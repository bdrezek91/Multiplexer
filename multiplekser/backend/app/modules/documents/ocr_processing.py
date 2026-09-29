"""Glowna logika przygotowania/OCR/postprocessingu wydawki.

Wydzielona z tasks.py bez zmiany zachowania, aby tasks.py pozostal tylko orkiestratorem Celery.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.modules.generator import pick_qty_razem
from app.modules.matcher import rules_from_db
from app.modules.matcher.special_rules import GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY
from app.modules.matcher.result import QUALITY_OK
from app.modules.ocr.chain import AllProvidersFailedError, OCRChainEventCallback
from app.modules.ocr.classify import classify_document
from app.modules.ocr.cooldown import OCRCooldownStore
from app.modules.ocr.image import classification_header_preview, downscale_image, is_blank_page, pdf_to_page_images
from app.modules.ocr.parsing import parse_float_loose
from app.modules.ocr.pipeline_elektryka import recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import OCRProviderError
from app.modules.ocr.verify import verify_ambiguous_quantities
from app.modules.products import Catalog
from app.modules.products.models import ProductModel

from .task_telemetry import _elapsed_ms

logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"
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
    classification_ms = 0
    ocr_matcher_ms = 0
    retry_wait_ms = 0
    for attempt in range(_MAX_ATTEMPTS):
        log_context = {"document_id": str(document.id), "ocr_attempt": attempt + 1}
        if attempt > 0:
            delay_s = _RETRY_DELAYS_S[attempt - 1]
            retry_wait_ms += delay_s * 1000
            time.sleep(delay_s)
        try:
            # Klasyfikacja potrzebuje tylko pola Elektryka/Hydraulika z naglowka.
            # Nie wysylamy drugi raz calej wydawki: pierwsza strona + gorne 45% + mniejszy JPEG.
            # Glowny OCR ponizej nadal dostaje pelne files.
            classification_files = [
                (classification_header_preview(files[0][0]), "image/jpeg")
            ] if files else files
            stage_started = time.perf_counter()
            try:
                classify_result = asyncio.run(classify_document(
                    classification_files, log_context=log_context, event_callback=event_callback,
                    cooldown_store=cooldown_store,
                ))
            finally:
                classification_ms += _elapsed_ms(stage_started)
            dzial = classify_result.dzial

            # Ten pomiar obejmuje zaladowanie katalogu + glowny request OCR + parsing +
            # bazowy matcher dla wszystkich pozycji. Matcher dziala wewnatrz pipeline, wiec
            # uczciwie mierzymy caly etap razem zamiast udawac osobny, niedokladny czas.
            stage_started = time.perf_counter()
            try:
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
            finally:
                ocr_matcher_ms += _elapsed_ms(stage_started)
            return classify_result, dzial, result, {
                "timing_retry_wait": retry_wait_ms,
                "timing_classification": classification_ms,
                "timing_ocr_matcher": ocr_matcher_ms,
            }
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
    plaski dict przechowywany w `items` - uzywana dla glownego odczytu."""
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




async def _verify_ambiguous_items(
    files: list[tuple[bytes, str]], items: list[dict], document_id: str,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
    dzial: str,
    quantity_marks: Optional[Mapping[str, tuple[bool, bool]]] = None,
    *,
    _verify_func=None,
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

    verify_func = _verify_func or verify_ambiguous_quantities
    results = await verify_func(
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

    # Jezeli zasilacz zostal juz rzeczywiscie odczytany z papierowej wydawki, NIE dopisujemy
    # drugiego automatycznie. Pozycja z kartki ma pierwszenstwo przed regułą "1 zasilacz do LED".
    # Naprawa 2026-09-29: w przeciwnym razie ten sam ZASILACZ LED 75W byl widoczny dwa razy.
    if any(it.get("match_kod") == _ZASILACZ_LED_KOD for it in items):
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
