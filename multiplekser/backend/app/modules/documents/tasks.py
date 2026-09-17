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
import re
import time
from datetime import datetime, timezone
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.generator import pick_qty_razem
from app.modules.matcher import rules_from_db
from app.modules.matcher.special_rules import GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY
from app.modules.matcher.result import QUALITY_OK
from app.modules.ocr.chain import AllProvidersFailedError, OCRChainEventCallback
from app.modules.ocr.classify import classify_document
from app.modules.ocr.cooldown import OCRCooldownStore, get_ocr_cooldown_store
from app.modules.ocr.image import downscale_image, is_blank_page, pdf_to_page_images
from app.modules.ocr.parsing import parse_float_loose
from app.modules.ocr.form_rows_elektryka import FORM_ROWS as _FORM_ROWS_ELEKTRYKA
from app.modules.ocr.form_rows_hydraulika import FORM_ROWS as _FORM_ROWS_HYDRAULIKA
from app.modules.ocr.pipeline_elektryka import OCRUnparsableResponseError, recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import OCRProviderError
from app.modules.ocr.row_groups import group_similar_rows
from app.modules.ocr.verify import verify_ambiguous_quantities, verify_row_group_alignment
from app.modules.products import Catalog
from app.modules.products.models import ProductModel

from . import repository
from .retention import prune_documents

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"

# Retry na PRZEJSCIOWE bledy sieci/dostepnosci (patrz docs/RAPORT_OCR_NIEZAWODNOSC_1.md) -
# WYLACZNIE (AllProvidersFailedError, OCRProviderError), czyli "zaden dostawca nie odpowiedzial
# poprawnie" - NIE obejmuje OCRUnparsableResponseError (model odpowiedzial, ale tresc byla
# bezuzyteczna - to problem jakosci danych/prompta, nie dostepnosci, wiec ponawianie na slepo
# nie jest tu wlasciwa reakcja). 3 proby razem (1 pierwsza + 2 ponowienia), rosnace opoznienie.
_MAX_ATTEMPTS = 3
_RETRY_DELAYS_S = (5, 15)

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


def _row_dict_from_ocritem(
    it, ilosc_wydana_raw, ilosc_zuzyta_raw, session: Session, *, ilosc_z_dodatkowej_kontroli: bool = False,
) -> dict:
    """Wspolna konwersja OCRItem/OCRItemHydraulika (ksztalt identyczny w obu pipeline'ach) na
    plaski dict przechowywany w `items` - uzywana zarowno dla glownego odczytu jak i pozycji
    dodanych/oflagowanych przez _check_row_group_alignment ponizej."""
    wydana = parse_float_loose(ilosc_wydana_raw) if ilosc_wydana_raw is not None else None
    zuzyta = parse_float_loose(ilosc_zuzyta_raw) if ilosc_zuzyta_raw is not None else None
    return {
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
        "ilosc_z_dodatkowej_kontroli": ilosc_z_dodatkowej_kontroli,
    }


_GROUP_MISMATCH_NOTE = (
    "Druga, niezależna kontrola AI wskazuje inną ilość dla tego wiersza (grupa podobnych "
    "wierszy formularza, np. różniących się przekrojem/wymiarem) - możliwe przesunięcie o "
    "jeden wiersz, zweryfikuj ręcznie na oryginale."
)


def _flag_group_mismatch(item: dict) -> None:
    item["needs_review"] = True
    item["ilosc_z_dodatkowej_kontroli"] = True
    existing = item.get("form_note") or ""
    item["form_note"] = f"{existing} | {_GROUP_MISMATCH_NOTE}" if existing else _GROUP_MISMATCH_NOTE


def _consensus(first: dict, second: dict) -> dict:
    """Zostawia TYLKO etykiety, dla ktorych dwie niezalezne dodatkowe kontrole (verify_first,
    verify_second w _check_row_group_alignment) zgadzaja sie ze soba co do obu ilosci - patrz
    uzasadnienie w miejscu wywolania. Brak zgodnosci (albo brak odpowiedzi jednej z prob dla
    danej etykiety) oznacza "nieustalone", nie trafia do dalszej analizy."""
    result = {}
    for label, r1 in first.items():
        r2 = second.get(label)
        if r2 is None:
            continue
        if r1.ilosc_wydana == r2.ilosc_wydana and r1.ilosc_zuzyta == r2.ilosc_zuzyta:
            result[label] = r1
    return result


async def _check_row_group_alignment(
    files: list[tuple[bytes, str]],
    items: list[dict],
    dzial: str,
    session: Session,
    document_id,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
    log_context: Mapping[str, object],
) -> None:
    """Druga, niezalezna kontrola AI dla grup niemal identycznych wierszy formularza (2026-09-17,
    realny przypadek produkcyjny: ilosc nalezaca do "Przewod 3x4" trafila do sasiedniego
    "Przewod 3x1,5" - patrz row_groups.py i prompt.py: _PODOBNE_WIERSZE_DOPISEK). Uruchamia
    dodatkowe zapytanie AI TYLKO gdy w dokumencie faktycznie wystapila taka grupa z jakakolwiek
    znaleziona iloscia (best-effort, nigdy nie blokuje calego dokumentu przy bledzie/braku
    wyniku - patrz verify_row_group_alignment). Zgodnosc obu odczytow (najczestszy przypadek) NIE
    zmienia niczego w `items`. Rozbieznosc: oznacza istniejaca pozycje (i cala reszte grupy) do
    recznej weryfikacji - NIGDY nie dodaje zgadywanej nowej pozycji (nawet gdy druga kontrola
    "znajdzie" ilosc dla wiersza pominietego przez glowny odczyt) - realny przypadek produkcyjny
    (2026-09-17) pokazal, ze druga kontrola bywa RÓWNIE bledna jak pierwsza (wskazuje inny, tez
    zly wiersz tej samej grupy), wiec automatyczne dodanie jej zgadniecia tylko zamienia jeden
    blad na dwa. Zamiast tego zostawia jawny trop w `document.ai_trace` (widoczny w UI jako
    "Przebieg AI") - decyzje co bylo faktycznie na kartce podejmuje czlowiek na oryginale."""
    form_rows = _FORM_ROWS_HYDRAULIKA if dzial == "hydraulika" else _FORM_ROWS_ELEKTRYKA
    all_groups = group_similar_rows(form_rows)
    if not all_groups:
        return

    active_labels = {
        item["rozpoznana_nazwa"] for item in items
        if item["ilosc_wydana"] is not None or item["ilosc_zuzyta"] is not None
    }
    at_risk_groups = [group for group in all_groups if any(label in active_labels for label in group)]
    if not at_risk_groups:
        return

    # Realny przypadek produkcyjny (2026-09-17): POJEDYNCZA druga kontrola jest sama w sobie
    # zbyt niestabilna, zeby jej ufac - w jednym przebiegu oflagowala 5 pozycji faktycznie
    # POPRAWNYCH (falszywe alarmy) i rownoczesnie przeoczyla prawdziwy blad (wskazala INNY zly
    # wiersz tej samej grupy niz za pierwszym razem). Wymagamy wiec zgodnosci DWOCH niezaleznych
    # dodatkowych odczytow ze soba, zanim cokolwiek oznaczymy - jesli druga i trzecia proba nie
    # zgadzaja sie ze soba, to sygnal, ze sama kontrola jest niepewna dla tego wiersza, wiec
    # ufamy glownemu odczytowi zamiast dodawac szum (patrz _consensus ponizej).
    verify_first = await verify_row_group_alignment(
        files, at_risk_groups, log_context=log_context,
        event_callback=event_callback, cooldown_store=cooldown_store,
    )
    if not verify_first:
        return
    verify_second = await verify_row_group_alignment(
        files, at_risk_groups, log_context=log_context,
        event_callback=event_callback, cooldown_store=cooldown_store,
    )
    verify_results = _consensus(verify_first, verify_second)
    if not verify_results:
        return

    items_by_label: dict[str, list[dict]] = {}
    for item in items:
        items_by_label.setdefault(item["rozpoznana_nazwa"], []).append(item)

    for group in at_risk_groups:
        for label in group:
            second = verify_results.get(label)
            if second is None:
                continue  # druga kontrola nie odpowiedziala dla tego ID - brak informacji, pomin

            existing = items_by_label.get(label, [])
            main_wydana = existing[0]["ilosc_wydana"] if existing else None
            main_zuzyta = existing[0]["ilosc_zuzyta"] if existing else None
            if second.ilosc_wydana == main_wydana and second.ilosc_zuzyta == main_zuzyta:
                continue  # zgodnosc obu niezaleznych odczytow - najczestszy przypadek, bez zmian

            if existing:
                for item in existing:
                    _flag_group_mismatch(item)
                try:
                    repository.log_row_group_flag(
                        session, document_id=document_id, dzial=dzial, rozpoznana_nazwa=label,
                        kind="mismatch_existing",
                        main_ilosc_wydana=main_wydana, main_ilosc_zuzyta=main_zuzyta,
                        second_ilosc_wydana=second.ilosc_wydana, second_ilosc_zuzyta=second.ilosc_zuzyta,
                    )
                except Exception:
                    logger.warning("Nie udalo sie zapisac logu row-group-flag", exc_info=True)
                continue

            if not second.found_anything:
                continue  # oba puste (roznica tylko np. 0 vs None) - nic do zrobienia

            # Glowny odczyt CALKOWICIE pominal ten wiersz, a druga kontrola znalazla dla niego
            # ilosc - typowy obraz "ofiary" przesuniecia wiersza. NIE dodajemy jednak zgadywanej
            # pozycji: realny przypadek produkcyjny (2026-09-17) pokazal, ze druga kontrola bywa
            # RÓWNIE bledna jak pierwsza (wskazala INNY, tez zly wiersz tej samej grupy) - dodanie
            # jej zgadniecia jako nowej pozycji tylko zamienilo jeden blad na dwa. Zamiast
            # fabrykowac dane, oflagowujemy do recznej weryfikacji WSZYSTKIE juz istniejace
            # pozycje tej samej grupy i zostawiamy jawny trop w "Przebiegu AI" (widoczny w UI) -
            # decyzje co faktycznie bylo na kartce podejmuje czlowiek na oryginale, nie zgadujemy.
            for other_label in group:
                for item in items_by_label.get(other_label, []):
                    _flag_group_mismatch(item)
            if event_callback is not None:
                try:
                    event_callback({
                        "status": "no_result",
                        "stage": "row_group_verification",
                        "provider": None,
                        "model": None,
                        "label": None,
                        "reason": (
                            f'Druga kontrola AI sugeruje, że w tej grupie wierszy mogła zostać '
                            f'pominięta pozycja "{label}" (możliwa ilość wydana: '
                            f'{second.ilosc_wydana}, zużyta: {second.ilosc_zuzyta}) - NIE dodano '
                            f'jej automatycznie (druga kontrola sama bywa niepewna), zweryfikuj '
                            f'ręcznie na oryginale.'
                        ),
                        "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
                        "target": label,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    logger.warning("Nie udalo sie zapisac zdarzenia AI dla row-group", exc_info=True)
            try:
                repository.log_row_group_flag(
                    session, document_id=document_id, dzial=dzial, rozpoznana_nazwa=label,
                    kind="missing_flagged_group",
                    main_ilosc_wydana=None, main_ilosc_zuzyta=None,
                    second_ilosc_wydana=second.ilosc_wydana, second_ilosc_zuzyta=second.ilosc_zuzyta,
                )
            except Exception:
                logger.warning("Nie udalo sie zapisac logu row-group-flag", exc_info=True)


async def _verify_ambiguous_items(
    files: list[tuple[bytes, str]], items: list[dict], document_id: str,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
    dzial: str,
    quantity_marks: Optional[Mapping[str, tuple[bool, bool]]] = None,
) -> None:
    """Dla pozycji z pusta ilosc w OBU kolumnach (typowy przypadek: "1" nierozroznialna od
    ptaszka przy pierwszym przebiegu) - jedna zbiorcza kontrola wszystkich wierszy. Nierozpoznane
    pozycje przechodza razem do kolejnego modelu, bez rownoleglego zalewania darmowego API.

    Pozycja z obiema pustymi iloscami trafia tu wylacznie dzieki wlasnej deklaracji glownego
    modelu ("ma_oznaczenie=true", patrz is_actionable_item). `quantity_marks` (dawniej: pikselowy
    detektor niebieskich zaznaczen dla Hydrauliki) jest wygaszony u zrodla - patrz
    pipeline_hydraulika.py i docs/RAPORT_OCR_NIEZAWODNOSC_4.md (zakladal jeden, staly fizyczny
    uklad wierszy kartki, a w obiegu jest ich co najmniej dwa) - wiec ten parametr zawsze
    przychodzi pusty/`None` z produkcji, zostawiony w sygnaturze wylacznie dla zgodnosci
    wstecznej z testami. Ufamy deklaracji glownego modelu bez dodatkowej weryfikacji, tak jak
    dla Elektryki."""
    marks = quantity_marks or {}
    targets = []
    for index, item in enumerate(items):
        has_wydana, has_zuzyta = marks.get(item["rozpoznana_nazwa"], (False, False))
        both_missing = item["ilosc_wydana"] is None and item["ilosc_zuzyta"] is None
        marked_column_missing = (
            (item["ilosc_wydana"] is None and has_wydana)
            or (item["ilosc_zuzyta"] is None and has_zuzyta)
        )
        if both_missing or marked_column_missing:
            targets.append(index)
    if not targets:
        return

    results = await verify_ambiguous_quantities(
        files,
        [items[i]["rozpoznana_nazwa"] for i in targets],
        dzial,
        log_context={"document_id": document_id},
        event_callback=event_callback,
        cooldown_store=cooldown_store,
    )
    for idx, result in zip(targets, results):
        if not result.found_anything:
            continue
        # Sygnal dla UI (patrz DocumentItemModel.ilosc_z_dodatkowej_kontroli) - ta ilosc
        # pochodzi z drugiej, mniej pewnej probie odczytu, nie z glownego modelu.
        items[idx]["ilosc_z_dodatkowej_kontroli"] = True
        # Kontrola uzupelnia tylko brakujaca kolumne. Poprawny wynik glownego OCR nie moze
        # zostac wyzerowany, gdy model kontrolny odczyta tylko druga z dwoch wartosci.
        if items[idx]["ilosc_wydana"] is None and result.ilosc_wydana is not None:
            items[idx]["ilosc_wydana"] = result.ilosc_wydana
        if items[idx]["ilosc_zuzyta"] is None and result.ilosc_zuzyta is not None:
            items[idx]["ilosc_zuzyta"] = result.ilosc_zuzyta
        items[idx]["ilosc_finalna"] = pick_qty_razem(
            items[idx]["ilosc_wydana"], items[idx]["ilosc_zuzyta"],
        )


# Na zyczenie uzytkownika (2026-08-31): kazda "tasma led" (wymuszana w special_rules.py na
# kod TASMA_LED_KOD) potrzebuje zasilacza - jedna sztuka ZA KAZDE wystapienie w dokumencie.
# Dopisywane tu, jako normalna, PERSYSTOWANA pozycja dokumentu (widoczna od razu na stronie
# weryfikacji, edytowalna jak kazda inna), nie tylko przy generowaniu TXT - stad NIE ma
# odpowiednika tej logiki w generatorze (patrz core_elektryka.py - usunieta stamtad, zeby nie
# doliczyc zasilacza podwojnie: raz tutaj jako zapisana pozycja, raz przy generowaniu).
_TASMA_LED_KOD = "TAŚMA LED DO DEKORÓW"
_ZASILACZ_LED_KOD = "ZASILACZ LED 75W"


def _append_auto_zasilacz_led(items: list[dict], dzial: str, session: Session) -> None:
    if dzial != "elektryka":
        return
    count = sum(1 for it in items if it.get("match_kod") == _TASMA_LED_KOD)
    if count == 0:
        return
    items.append({
        "rozpoznana_nazwa": "Zasilacz LED 75W",
        "ilosc_wydana": None,
        "ilosc_zuzyta": None,
        "ilosc_finalna": float(count),
        "match_quality": QUALITY_OK,
        "match_score": 1.0,
        "off_form": False,
        "needs_review": False,
        "form_note": (
            "Dodano automatycznie - 1 szt. za każde wystąpienie taśmy LED w tym dokumencie."
        ),
        "uwagi": "",
        "confidence": None,
        "matched_product_id": _resolve_product_id(session, _ZASILACZ_LED_KOD),
        "match_kod": _ZASILACZ_LED_KOD,
        "match_nazwa": "Zasilacz LED 75W",
        "match_jm": "SZT",
        "ilosc_z_dodatkowej_kontroli": False,
    })


# Na zyczenie uzytkownika (2026-09-10): "Gniazdo podwojne [kolor] [kraj] podtynkowe" nie ma
# wlasnego kodu w Optimie - fizycznie sklada sie z DWOCH pojedynczych gniazd podtynkowych z
# klapka. special_rules.py juz ustawil poprawny kod POJEDYNCZEGO gniazda (patrz
# GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY) - tu tylko PODWAJAMY ilosc, bo MatchResult (uzywany przy
# dopasowywaniu) nie niesie ze soba ilosci, wiec special_rules.py nie moze tego zrobic sam.
_PODWOJNE_WZORZEC = re.compile(r"\bpodw[oó]jne\b", re.IGNORECASE)


def _podwoj_ilosc_gniazda_podwojnego_podtynkowego(items: list[dict]) -> None:
    for it in items:
        kod = it.get("match_kod")
        # `.strip()` - jeden z kodow w katalogu ("...GRAFIT POLSKIE") ma spacje koncowa w samych
        # danych zrodlowych (Catalog.find_by_kod juz to toleruje przez fallback trim przy
        # dopasowywaniu, tu porownujemy tak samo, zeby nie ominac tego wariantu).
        if kod is None or kod.strip() not in GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY:
            continue
        if not _PODWOJNE_WZORZEC.search(it.get("rozpoznana_nazwa") or ""):
            continue
        for pole in ("ilosc_wydana", "ilosc_zuzyta", "ilosc_finalna"):
            wartosc = it.get(pole)
            if wartosc is not None:
                it[pole] = wartosc * 2
        dopisek = "Gniazdo podwójne = 2x gniazdo pojedyncze podtynkowe z klapką - ilość podwojona automatycznie."
        it["uwagi"] = f"{it['uwagi']} {dopisek}".strip() if it.get("uwagi") else dopisek


def _download_and_prepare(get_storage, file_key: str, mime: str) -> list[tuple[bytes, str]]:
    """Pobiera jeden plik ze storage i przygotowuje do wyslania do AI. PDF jest rozbijany na
    OSOBNE obrazy, po jednym na strone (patrz ocr/image.py: pdf_to_page_images, dlaczego -
    natywne wysylanie calego PDF jako jednego pliku bylo mniej niezawodne na gestych,
    wielostronicowych dokumentach) - stad lista, nie pojedynczy plik. Zwykly obraz zostaje
    pojedynczym elementem listy, tylko przeskalowanym (patrz ocr/image.py, dlaczego)."""
    raw = get_storage().download(file_key)
    if mime == _PDF_MIME:
        pages = pdf_to_page_images(raw)
        # Pomija prawie puste strony (2026-09-17, patrz ocr/image.py: is_blank_page) - typowo
        # "widmowe" przebicie druku z drugiej strony kartki na cienkim papierze. Nigdy nie
        # filtruje WSZYSTKICH stron na raz (bezpieczny fallback do niefiltrowanej listy), zeby
        # bledna/zbyt agresywna detekcja nigdy nie zostawila dokumentu bez zadnego obrazu.
        non_blank_pages = [page for page in pages if not is_blank_page(page)]
        pages = non_blank_pages or pages
        return [(downscale_image(page), "image/jpeg") for page in pages]
    return [(downscale_image(raw), "image/jpeg")]


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
        # jednej papierowej wydawki, ktorej nie da sie zmiescic na jednym zdjeciu, albo kolejne
        # strony wielostronicowego PDF ze skanera rozbite na obrazy - patrz _download_and_prepare
        # powyzej i historia czatu) - patrz tez ocr/providers.py. Pierwszy plik to zawsze
        # document.file_key/mime (wsteczna zgodnosc), kolejne to document.extra_files w kolejnosci
        # `sequence`. Wszystkie razem trafiaja do Gemini w jednym zapytaniu.
        files = list(_download_and_prepare(get_storage, document.file_key, document.mime))
        for extra in document.extra_files:
            files += _download_and_prepare(get_storage, extra.file_key, extra.mime)

        # Krok Hydraulika-3: klasyfikacja dzialu PRZED pelnym odczytem (tani, pierwszy przebieg
        # Gemini - patrz ocr/classify.py) - dopiero po niej wiadomo, ktory katalog/prompt/matcher
        # uzyc. Brak recznego przelacznika w UI: uzytkownik chce w pelni automatycznego wykrywania.
        classify_result, dzial, result = _classify_and_recognize(
            files, session, document, save_ai_event, cooldown_store,
        )

        items = [
            _row_dict_from_ocritem(it, it.ilosc_wydana, it.ilosc_zuzyta, session)
            for it in result.pozycje
        ]

        asyncio.run(_verify_ambiguous_items(
            files, items, document_id, save_ai_event, cooldown_store, dzial,
        ))

        asyncio.run(_check_row_group_alignment(
            files, items, dzial, session, document.id,
            save_ai_event, cooldown_store, {"document_id": document_id},
        ))

        _append_auto_zasilacz_led(items, dzial, session)
        _podwoj_ilosc_gniazda_podwojnego_podtynkowego(items)

        repository.mark_done(
            session, document,
            numer_projektu=result.numer_projektu, used_provider=result.used_provider,
            rejected_count=result.rejected_count, items=items,
            dzial=dzial, dzial_confidence=classify_result.confidence,
            pracownik=result.pracownik, numer_plomby=result.numer_plomby,
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
    finally:
        try:
            prune_documents(session, get_storage(), limit=settings.document_retention_limit)
        except Exception:
            # Awaria sprzatania nie moze zmienic wyniku poprawnie zakonczonej analizy.
            session.rollback()
            logger.exception("Retencja dokumentow nie powiodla sie")


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
