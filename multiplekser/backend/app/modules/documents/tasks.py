"""Task Celery przetwarzania OCR (Etap 7) - port glownej sciezki runAI() z monolitu, teraz w tle
zamiast blokujaco w zadaniu HTTP (endpoint synchroniczny z Etapu 6 byl swiadomie oznaczony jako
ryzyko do naprawy - patrz docs/RAPORT_ETAP_6.md).

`run_ocr_task(document_id, session)` to CZYSTA logika, testowalna bez brokera/workera - przyjmuje
sesje z zewnatrz (patrz tests/test_documents_task.py, ktore uzywaja tej samej `db_session` co
reszta testow integracyjnych). `process_ocr_document()` to cienki wrapper zarejestrowany w Celery,
ktory otwiera WLASNA sesje (bo w prawdziwym workerze nie ma z kim jej dzielic) i deleguje dalej -
oddziela "co robi zadanie" od "jak Celery je uruchamia", tak jak scripts/import_*.py oddzielaja
logike importu od swojego cienkiego CLI.
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.modules.generator import pick_qty_razem
from app.modules.matcher import rules_from_db
from app.modules.ocr.chain import AllProvidersFailedError, OCRChainEventCallback
from app.modules.ocr.classify import classify_document
from app.modules.ocr.cooldown import OCRCooldownStore, get_ocr_cooldown_store
from app.modules.ocr.image import downscale_image
from app.modules.ocr.parsing import parse_float_loose
from app.modules.ocr.pipeline_elektryka import OCRUnparsableResponseError, recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import OCRProviderError
from app.modules.ocr.verify import verify_ambiguous_quantity
from app.modules.products import Catalog
from app.modules.products.models import ProductModel

from . import repository

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"

# Retry na PRZEJSCIOWE bledy sieci/dostepnosci (patrz docs/RAPORT_OCR_NIEZAWODNOSC_1.md) -
# WYLACZNIE (AllProvidersFailedError, OCRProviderError), czyli "zaden dostawca nie odpowiedzial
# poprawnie" - NIE obejmuje OCRUnparsableResponseError (model odpowiedzial, ale tresc byla
# bezuzyteczna - to problem jakosci danych/prompta, nie dostepnosci, wiec ponawianie na slepo
# nie jest tu wlasciwa reakcja). 3 proby razem (1 pierwsza + 2 ponowienia), rosnace opoznienie.
_MAX_ATTEMPTS = 3
_RETRY_DELAYS_S = (5, 15)

# Druga, waska proba odczytu ilosci (patrz app/modules/ocr/verify.py) - ograniczona do
# rozsadnej liczby pozycji na dokument, zeby pojedynczy, mocno uszkodzony skan (duzo pustych
# wierszy) nie wygenerowal lawiny dodatkowych zapytan do AI.
_MAX_VERIFY_ITEMS = 8


def _resolve_product_id(session: Session, kod):
    if not kod:
        return None
    row = session.query(ProductModel.id).filter(ProductModel.kod == kod).first()
    return row[0] if row else None


def _classify_and_recognize(
    files: list[tuple[bytes, str]], session: Session, document,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
):
    """Klasyfikacja dzialu + pelny odczyt, z automatycznym ponowieniem na przejsciowe bledy
    dostepnosci AI (patrz _MAX_ATTEMPTS/_RETRY_DELAYS_S wyzej). Klasyfikacja jest ponawiana
    razem z odczytem (nie osobno) - jest tania/szybka, a w praktyce oba kroki zawodza z tego
    samego powodu (brak sieci/limit), wiec nie ma sensu ich rozdzielac. `files` - jeden element
    dla zwyklego skanu/PDF, wiecej gdy dokument sklada sie z kilku osobnych plikow (np. dwa
    zdjecia z telefonu = dwie strony jednej papierowej wydawki, patrz historia czatu) - wszystkie
    trafiaja do Gemini w JEDNYM zapytaniu (patrz ocr/providers.py), prompt uczy model laczyc je
    w jeden wynik."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        log_context = {"document_id": str(document.id), "ocr_attempt": attempt + 1}
        if attempt > 0:
            time.sleep(_RETRY_DELAYS_S[attempt - 1])
        try:
            classify_result = asyncio.run(classify_document(
                files, log_context=log_context, event_callback=event_callback,
                cooldown_store=cooldown_store,
            ))
            dzial = classify_result.dzial

            catalog = Catalog.from_db(session, dzial=dzial)
            if dzial == "hydraulika":
                result = asyncio.run(
                    recognize_document_hydraulika(
                        files, catalog, magazyn=document.magazyn, log_context=log_context,
                        event_callback=event_callback,
                        cooldown_store=cooldown_store,
                    )
                )
            else:
                special_rules = rules_from_db(session)
                result = asyncio.run(
                    recognize_document(
                        files, catalog, special_rules, magazyn=document.magazyn,
                        log_context=log_context, event_callback=event_callback,
                        cooldown_store=cooldown_store,
                    )
                )
            return classify_result, dzial, result
        except (AllProvidersFailedError, OCRProviderError) as exc:
            last_exc = exc
            logger.warning(
                "OCR - przejsciowy blad dostepnosci, proba %s/%s",
                attempt + 1, _MAX_ATTEMPTS,
                extra={"document_id": str(document.id), "attempt": attempt + 1, "error": str(exc)},
            )
    raise last_exc  # wyczerpano proby - blad koncowy, jak dotad ida do Document.status="error"


async def _verify_ambiguous_items(
    files: list[tuple[bytes, str]], items: list[dict], document_id: str,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
) -> None:
    """Dla pozycji z pusta ilosc w OBU kolumnach (typowy przypadek: "1" nierozroznialna od
    ptaszka przy pierwszym przebiegu) - druga, waska proba per-wiersz, rownolegle. Modyfikuje
    `items` w miejscu; kazdy blad pojedynczej proby jest juz pochloniety w verify_ambiguous_quantity
    (best-effort), wiec tu nie ma juz obslugi wyjatkow do zrobienia."""
    targets = [
        i for i, it in enumerate(items)
        if it["ilosc_wydana"] is None and it["ilosc_zuzyta"] is None
    ][:_MAX_VERIFY_ITEMS]
    if not targets:
        return

    results = await asyncio.gather(
        *(
            verify_ambiguous_quantity(
                files, items[i]["rozpoznana_nazwa"], log_context={"document_id": document_id},
                event_callback=event_callback,
                cooldown_store=cooldown_store,
            )
            for i in targets
        )
    )
    for idx, result in zip(targets, results):
        if not result.found_anything:
            continue
        items[idx]["ilosc_wydana"] = result.ilosc_wydana
        items[idx]["ilosc_zuzyta"] = result.ilosc_zuzyta
        items[idx]["ilosc_finalna"] = pick_qty_razem(result.ilosc_wydana, result.ilosc_zuzyta)


def _download_and_prepare(get_storage, file_key: str, mime: str) -> tuple[bytes, str]:
    """Pobiera jeden plik ze storage i przygotowuje do wyslania do AI - PDF wysylany natywnie,
    obraz najpierw przeskalowany (patrz ocr/image.py, dlaczego)."""
    raw = get_storage().download(file_key)
    if mime == _PDF_MIME:
        return raw, _PDF_MIME
    return downscale_image(raw), "image/jpeg"


def run_ocr_task(document_id: str, session: Session) -> None:
    from .storage import get_storage  # lazy import - unika inicjalizacji klienta S3 przy imporcie modulu

    document = repository.get_document(session, document_id)
    if document is None:
        return

    repository.mark_processing(session, document)
    logger.info("OCR - start przetwarzania", extra={"document_id": document_id})

    def save_ai_event(event: dict[str, object]) -> None:
        repository.append_ai_trace_event(session, document, event)

    cooldown_store = get_ocr_cooldown_store()

    try:
        # Wiele plikow = wiele osobnych stron TEGO SAMEGO dokumentu (np. dwa zdjecia z telefonu
        # jednej papierowej wydawki, ktorej nie da sie zmiescic na jednym zdjeciu tak jak wielo-
        # stronicowy PDF ze skanera) - patrz historia czatu. Pierwszy plik to zawsze
        # document.file_key/mime (wsteczna zgodnosc), kolejne to document.extra_files w kolejnosci
        # `sequence`. Wszystkie razem trafiaja do Gemini w jednym zapytaniu (ocr/providers.py).
        files = [_download_and_prepare(get_storage, document.file_key, document.mime)]
        files += [
            _download_and_prepare(get_storage, extra.file_key, extra.mime)
            for extra in document.extra_files
        ]

        # Krok Hydraulika-3: klasyfikacja dzialu PRZED pelnym odczytem (tani, pierwszy przebieg
        # Gemini - patrz ocr/classify.py) - dopiero po niej wiadomo, ktory katalog/prompt/matcher
        # uzyc. Brak recznego przelacznika w UI: uzytkownik chce w pelni automatycznego wykrywania.
        classify_result, dzial, result = _classify_and_recognize(
            files, session, document, save_ai_event, cooldown_store,
        )

        items = []
        for it in result.pozycje:
            wydana = parse_float_loose(it.ilosc_wydana) if it.ilosc_wydana is not None else None
            zuzyta = parse_float_loose(it.ilosc_zuzyta) if it.ilosc_zuzyta is not None else None
            items.append({
                "rozpoznana_nazwa": it.rozpoznana_nazwa,
                "ilosc_wydana": wydana,
                "ilosc_zuzyta": zuzyta,
                # Domyslna ilosc do weryfikacji/generowania - pickQty('razem') z monolitu (zuzyta
                # jesli podana, inaczej wydana). Uzytkownik moze nadpisac przez PATCH przed
                # wygenerowaniem (patrz RAPORT_ETAP_9.md).
                "ilosc_finalna": pick_qty_razem(wydana, zuzyta),
                "match_quality": it.match.quality,
                "match_score": it.match.ratio,
                "off_form": it.off_form,
                "needs_review": it.needs_review,
                "form_note": it.form_note,
                "uwagi": it.uwagi,
                "confidence": it.confidence,
                "matched_product_id": _resolve_product_id(session, it.match.kod),
                "match_kod": it.match.kod,
                "match_nazwa": it.match.nazwa,
                "match_jm": it.match.jm_override,
            })

        asyncio.run(_verify_ambiguous_items(
            files, items, document_id, save_ai_event, cooldown_store,
        ))

        repository.mark_done(
            session, document,
            numer_projektu=result.numer_projektu, used_provider=result.used_provider,
            rejected_count=result.rejected_count, items=items,
            dzial=dzial, dzial_confidence=classify_result.confidence,
        )
        logger.info(
            "OCR - zakonczone sukcesem",
            extra={
                "document_id": document_id, "dzial": dzial, "used_provider": result.used_provider,
                "pozycje": len(items), "rejected_count": result.rejected_count,
            },
        )
    except (OCRUnparsableResponseError, AllProvidersFailedError, OCRProviderError) as exc:
        repository.mark_error(session, document, str(exc))
        logger.error("OCR - zakonczone bledem", extra={"document_id": document_id, "error": str(exc)})
    except Exception as exc:  # zabezpieczenie - blad nie moze zniknac w workerze bez sladu w Document.status
        repository.mark_error(session, document, f"Nieoczekiwany blad: {exc}")
        logger.exception("OCR - nieoczekiwany blad", extra={"document_id": document_id})


@celery_app.task(name="documents.process_ocr")
def process_ocr_document(document_id: str) -> None:
    session = SessionLocal()
    try:
        run_ocr_task(document_id, session)
    finally:
        session.close()


def dispatch_ocr_task(document_id: str) -> None:
    """Zleca przetwarzanie dokumentu do Celery. Router wywoluje WYLACZNIE ta funkcje, nigdy
    `process_ocr_document` bezposrednio - cienka warstwa oddzielajaca "co robi zadanie" od
    "jak jest zlecane"."""
    process_ocr_document.delay(document_id)
