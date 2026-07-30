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
import threading

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.generator import pick_qty_razem
from app.modules.matcher import rules_from_db
from app.modules.ocr.chain import AllProvidersFailedError
from app.modules.ocr.classify import classify_document
from app.modules.ocr.image import downscale_image
from app.modules.ocr.parsing import parse_float_loose
from app.modules.ocr.pipeline import OCRUnparsableResponseError, recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import OCRProviderError
from app.modules.products import Catalog
from app.modules.products.models import ProductModel

from . import repository

_PDF_MIME = "application/pdf"


def _resolve_product_id(session: Session, kod):
    if not kod:
        return None
    row = session.query(ProductModel.id).filter(ProductModel.kod == kod).first()
    return row[0] if row else None


def run_ocr_task(document_id: str, session: Session) -> None:
    from .storage import get_storage  # lazy import - unika inicjalizacji klienta S3 przy imporcie modulu

    document = repository.get_document(session, document_id)
    if document is None:
        return

    repository.mark_processing(session, document)

    try:
        raw = get_storage().download(document.file_key)
        if document.mime == _PDF_MIME:
            file_bytes, mime = raw, _PDF_MIME
        else:
            file_bytes, mime = downscale_image(raw), "image/jpeg"

        # Krok Hydraulika-3: klasyfikacja dzialu PRZED pelnym odczytem (tani, pierwszy przebieg
        # Gemini - patrz ocr/classify.py) - dopiero po niej wiadomo, ktory katalog/prompt/matcher
        # uzyc. Brak recznego przelacznika w UI: uzytkownik chce w pelni automatycznego wykrywania.
        classify_result = asyncio.run(classify_document(file_bytes, mime))
        dzial = classify_result.dzial

        catalog = Catalog.from_db(session, dzial=dzial)
        if dzial == "hydraulika":
            result = asyncio.run(
                recognize_document_hydraulika(file_bytes, mime, catalog, magazyn=document.magazyn)
            )
        else:
            special_rules = rules_from_db(session)
            result = asyncio.run(
                recognize_document(file_bytes, mime, catalog, special_rules, magazyn=document.magazyn)
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

        repository.mark_done(
            session, document,
            numer_projektu=result.numer_projektu, used_provider=result.used_provider,
            rejected_count=result.rejected_count, items=items,
            dzial=dzial, dzial_confidence=classify_result.confidence,
        )
    except (OCRUnparsableResponseError, AllProvidersFailedError, OCRProviderError) as exc:
        repository.mark_error(session, document, str(exc))
    except Exception as exc:  # zabezpieczenie - blad nie moze zniknac w workerze bez sladu w Document.status
        repository.mark_error(session, document, f"Nieoczekiwany blad: {exc}")


@celery_app.task(name="documents.process_ocr")
def process_ocr_document(document_id: str) -> None:
    session = SessionLocal()
    try:
        run_ocr_task(document_id, session)
    finally:
        session.close()


def dispatch_ocr_task(document_id: str) -> None:
    """Uruchamia przetwarzanie dokumentu - Celery/Redis normalnie (produkcja/Docker), albo
    watek w tym samym procesie w trybie Multiplekser Portable (`settings.desktop_mode`,
    patrz docs/RAPORT_PORTABLE_1.md) - dla jednego uzytkownika na wlasnym komputerze osobny
    broker/worker to zbedny narzut, ktory wymagalby doinstalowania Redis. Router wywoluje
    WYLACZNIE ta funkcje, nigdy `process_ocr_document` bezposrednio - dzieki temu przelaczenie
    trybu nie wymaga zmian poza konfiguracja."""
    if settings.desktop_mode:
        def _run() -> None:
            session = SessionLocal()
            try:
                run_ocr_task(document_id, session)
            finally:
                session.close()

        threading.Thread(target=_run, daemon=True).start()
    else:
        process_ocr_document.delay(document_id)
