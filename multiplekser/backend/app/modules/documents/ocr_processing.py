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
from app.modules.ocr.verify import VerifyResult, verify_ambiguous_quantities
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
        if dzial == "hydraulika":
            # W Hydraulice najtrudniejszy przypadek to odreczna "1" podobna do "/" oraz
            # pozioma kreska "-" oznaczajaca brak. Dlatego weryfikujemy:
            # - kazdy wiersz z co najmniej jedna brakujaca kolumna (np. 3 / 1,5),
            # - kazda odczytana jedynke, zeby skreslenie nie zostalo uznane za 1.
            hyd_needs_check = (
                item["ilosc_wydana"] is None
                or item["ilosc_zuzyta"] is None
                or item["ilosc_wydana"] == 1
                or item["ilosc_zuzyta"] == 1
            )
            if hyd_needs_check:
                targets.append(index)
        elif both_missing or marked_column_missing:
            targets.append(index)
    if not targets:
        return

    verify_func = _verify_func or verify_ambiguous_quantities
    target_names = [items[i]["rozpoznana_nazwa"] for i in targets]
    results = await verify_func(
        files,
        target_names,
        dzial,
        log_context={"document_id": document_id},
        event_callback=event_callback,
        cooldown_store=cooldown_store,
    )

    # Hydraulika: przy odręcznych "1" podobnych do "/" pojedynczy request bywa niestabilny.
    # Drugi, niezależny odczyt tym samym mechanizmem działa jako konsensus: brak uzupełniamy
    # wyłącznie wtedy, gdy OBA odczyty zwracają tę samą dodatnią wartość. Rozbieżność -> null
    # i ręczna weryfikacja zamiast ryzyka wpisania poziomej kreski "-" jako cyfry 1.
    disagreements: set[int] = set()
    if dzial == "hydraulika":
        confirmation = await verify_func(
            files,
            target_names,
            dzial,
            log_context={"document_id": document_id, "quantity_consensus_pass": 2},
            event_callback=None,
            cooldown_store=cooldown_store,
        )
        merged = []
        for pos, (first, second) in enumerate(zip(results, confirmation)):
            def agreed(a, b):
                if a is None or b is None:
                    return None
                return a if abs(float(a) - float(b)) < 1e-9 else None

            wydana = agreed(first.ilosc_wydana, second.ilosc_wydana)
            zuzyta = agreed(first.ilosc_zuzyta, second.ilosc_zuzyta)
            if (
                (first.ilosc_wydana is not None or second.ilosc_wydana is not None)
                and wydana is None
            ) or (
                (first.ilosc_zuzyta is not None or second.ilosc_zuzyta is not None)
                and zuzyta is None
            ):
                disagreements.add(pos)
            merged.append(VerifyResult(wydana, zuzyta))
        results = merged

        # Najtrudniejsza wartosc to 1 (ukosna kreska podobna do "/" vs poziome "-").
        # Jesli dwa pierwsze odczyty zgodnie zwrocily 1, prosimy o trzeci glos TYLKO dla
        # takich pozycji. Jedynke akceptujemy dopiero przy zgodzie 3/3.
        third_positions = [
            pos for pos, result in enumerate(results)
            if result.ilosc_wydana == 1 or result.ilosc_zuzyta == 1
        ]
        if third_positions:
            third_names = [target_names[pos] for pos in third_positions]
            third_results = await verify_func(
                files,
                third_names,
                dzial,
                log_context={"document_id": document_id, "quantity_consensus_pass": 3},
                event_callback=None,
                cooldown_store=cooldown_store,
            )
            for pos, third in zip(third_positions, third_results):
                result = results[pos]
                wydana = result.ilosc_wydana
                zuzyta = result.ilosc_zuzyta
                if wydana == 1 and third.ilosc_wydana != 1:
                    wydana = None
                    disagreements.add(pos)
                if zuzyta == 1 and third.ilosc_zuzyta != 1:
                    zuzyta = None
                    disagreements.add(pos)
                results[pos] = VerifyResult(wydana, zuzyta)

    for pos, (idx, result) in enumerate(zip(targets, results)):
        item = items[idx]
        changed = False

        if dzial == "hydraulika":
            # Brakujace pola uzupelniamy tylko zgodnym konsensusem; jedynka wymaga 3/3.
            for field, verified in (
                ("ilosc_wydana", result.ilosc_wydana),
                ("ilosc_zuzyta", result.ilosc_zuzyta),
            ):
                original = item[field]
                if original is None and verified is not None:
                    item[field] = verified
                    changed = True
                elif original == 1:
                    # Jedynka z glownego OCR musi byc potwierdzona przez konsensus. Jesli dwie
                    # kontrole nie potwierdzily 1, usuwamy ja zamiast ryzykowac skreslenie/"-".
                    if verified != 1:
                        item[field] = None
                        changed = True
                        disagreements.add(pos)
        else:
            if item["ilosc_wydana"] is None and result.ilosc_wydana is not None:
                item["ilosc_wydana"] = result.ilosc_wydana
                changed = True
            if item["ilosc_zuzyta"] is None and result.ilosc_zuzyta is not None:
                item["ilosc_zuzyta"] = result.ilosc_zuzyta
                changed = True

        if pos in disagreements:
            item["needs_review"] = True
            note = "Kontrole AI nie zgodziły się co do ilości - sprawdź na oryginale."
            current = str(item.get("form_note") or "").strip()
            if note not in current:
                item["form_note"] = f"{current} | {note}" if current else note

        if changed or result.found_anything:
            item["ilosc_z_dodatkowej_kontroli"] = True
        item["ilosc_finalna"] = pick_qty_razem(item["ilosc_wydana"], item["ilosc_zuzyta"])


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


# Na zyczenie uzytkownika (2026-09-10, rozszerzone 2026-09-30): "Gniazdo podwojne
# [kolor] [kraj] podtynkowe" nie ma wlasnego kodu w Optimie. Fizyczny komplet to DWA
# pojedyncze gniazda z klapka + JEDNA ramka podwojna w tym samym kolorze + JEDNA puszka
# instalacyjna 2-polowa podtynkowa. special_rules.py ustawia kod pojedynczego gniazda, a tutaj
# materializujemy pozostale elementy zestawu i mnozymy gniazdo x2.
_PODWOJNE_WZORZEC = re.compile(r"\bpodw[oó]jne\b", re.IGNORECASE)
_PUSZKA_2_POLOWA_KOD = "PUSZKA INSTALACYJNA 2 POLOWA PODTYNKOWA"
_RAMKA_PODWOJNA_BY_GNIAZDO_KOD = {
    "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE NIEMIECKIE": "RAMKA PODWÓJNA BIAŁA",
    "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE POLSKIE": "RAMKA PODWÓJNA BIAŁA",
    "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ GRAFIT NIEMIECKIE": "RAMKA PODWÓJNA ANTRACYT",
    "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ GRAFIT POLSKIE": "RAMKA PODWÓJNA ANTRACYT",
}


def _auto_component_item(
    *, source: dict, kod: str, session: Session, opis: str,
) -> dict:
    product = session.query(ProductModel).filter(ProductModel.kod == kod).first()
    nazwa = product.nazwa if product is not None else kod
    jm = product.jm if product is not None else "SZT"
    return {
        "rozpoznana_nazwa": nazwa,
        "ilosc_wydana": source.get("ilosc_wydana"),
        "ilosc_zuzyta": source.get("ilosc_zuzyta"),
        "ilosc_finalna": source.get("ilosc_finalna"),
        "match_quality": QUALITY_OK,
        "match_score": 1.0,
        "off_form": False,
        "needs_review": False,
        "form_note": f"Dodano automatycznie - {opis}",
        "uwagi": "",
        "confidence": None,
        "matched_product_id": product.id if product is not None else None,
        "match_kod": kod,
        "match_nazwa": nazwa,
        "match_jm": jm,
        "ilosc_z_dodatkowej_kontroli": False,
    }


def _append_auto_osprzet_gniazda_podwojnego_podtynkowego(
    items: list[dict], session: Session,
) -> None:
    """Do każdego podwójnego gniazda podtynkowego dodaje 1 ramkę + 1 puszkę na zestaw."""
    additions: list[dict] = []
    for it in list(items):
        kod = str(it.get("match_kod") or "").strip()
        if kod not in GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY:
            continue
        if not _PODWOJNE_WZORZEC.search(it.get("rozpoznana_nazwa") or ""):
            continue
        ramka_kod = _RAMKA_PODWOJNA_BY_GNIAZDO_KOD.get(kod)
        if ramka_kod is None:
            continue
        additions.append(_auto_component_item(
            source=it,
            kod=ramka_kod,
            session=session,
            opis="1 ramka podwójna na każde gniazdo podwójne podtynkowe.",
        ))
        additions.append(_auto_component_item(
            source=it,
            kod=_PUSZKA_2_POLOWA_KOD,
            session=session,
            opis="1 puszka instalacyjna 2-polowa podtynkowa na każde gniazdo podwójne podtynkowe.",
        ))
    items.extend(additions)


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
