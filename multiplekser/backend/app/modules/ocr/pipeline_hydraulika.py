"""Pipeline OCR dla dzialu Hydraulika - odpowiednik ocr/pipeline.py (Elektryka), OSOBNA funkcja
(ten sam wzorzec co parser/matcher - patrz CLAUDE.md, "Decyzja architektoniczna"). Port glownej
sciezki runAI()/snapToKnownItem() z Multipekser_Hydraulika.html.

Roznice wobec pipeline.py (Elektryka), wszystkie 1:1 ze zrodla:
- prompt.AI_OCR_PROMPT_HYDRAULIKA (nie AI_OCR_PROMPT),
- dwupoziomowe dopasowanie do znanej pozycji: FORM_ROWS -> ADDITIONAL_ROWS
  (form_rows_hydraulika.snap_to_known_item_hydraulika), nie jednopoziomowe jak w Elektryce,
- BRAK odpowiednika reconcile_form_row() - Hydraulika nigdy nie miala tej poprawki w zrodle
  (patrz docstring form_rows_hydraulika.py),
- match_against_catalog_hydraulika() zamiast match_against_catalog() - bez special_rules
  (DEFAULT_SPECIAL_RULES_HYDRAULIKA jest pusta, patrz matcher/core.py).

Lokalny pikselowy detektor niebieskich zaznaczen (discover_hydraulika_quantity_marks,
verification_image.py) byl tu wczesniej uzywany jako siatka bezpieczenstwa dla wierszy
pominietych przez glowny model. Wylaczony (2026-08-24) - zaklada jeden, staly fizyczny uklad
wierszy kartki (_HYDRAULIKA_PAGES), a w obiegu sa co najmniej dwie rozne wersje papierowej
wydawki (z i bez wiersza "Blat kuchenny 1650x600"). Na kartce bez tego wiersza cala reszta
strony wychodzi przesunieta o jeden wiersz, co dawalo pozornie losowe falszywe
zaznaczenia/pominiecia - trzeci taki przypadek po dwoch wczesniejszych poprawkach
(RAPORT_OCR_NIEZAWODNOSC_3.md), whack-a-mole bez konca dopoki formularz nie ma jednego,
ustalonego ukladu. Patrz docs/RAPORT_OCR_NIEZAWODNOSC_4.md.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional

from app.modules.matcher import MatchResult, match_against_catalog_hydraulika
from app.modules.products import Catalog
from app.modules.parser.shared import strip_diacritics

from .chain import AllProvidersFailedError, OCRChainEventCallback, OCRChainStep, run_ocr_chain
from .cooldown import OCRCooldownStore
from .form_rows_hydraulika import snap_to_known_item_hydraulika
from .parsing import extract_json, is_actionable_item, is_valid_ocr_response, validate_item
from .pipeline_elektryka import OCRUnparsableResponseError, _clean_header_text, normalize_project_number
from .prompt import AI_OCR_PROMPT_HYDRAULIKA


@dataclass
class OCRItemHydraulika:
    rozpoznana_nazwa: str
    ilosc_wydana: Optional[str]
    ilosc_zuzyta: Optional[str]
    uwagi: str
    confidence: Optional[float]
    needs_review: bool
    off_form: bool
    form_note: str
    match: MatchResult


@dataclass
class OCRResultHydraulika:
    numer_projektu: Optional[str]
    pracownik: Optional[str]
    numer_plomby: Optional[str]
    pozycje: list[OCRItemHydraulika]
    used_provider: str
    rejected_count: int


def _decode_literal_qty(raw_value: object) -> tuple[bool, Optional[str]]:
    """Interpretuje SUROWY niebieski znak z formularza Hydrauliki.

    Zwraca (czy_pole_raw_bylo_dostarczone, wartosc_do_dalszego_parsowania).
    "/" to charakterystyczna reczna jedynka, pozioma kreska to brak. Przecinek dziesietny
    normalizujemy tutaj do kropki, bo wspolny parse_float_loose celowo nie obsluguje przecinka.
    """
    if raw_value is None:
        return True, None
    text = str(raw_value).strip()
    if not text:
        return True, None

    compact = re.sub(r"\s+", "", text)
    if compact in {"-", "—", "–", "_"}:
        return True, None
    if compact in {"/", "\\", "|"}:
        return True, "1"

    # Gdy model mimo instrukcji zostawi w raw takze czarny ptaszek, ignorujemy go.
    cleaned = re.sub(r"[✓✔Vv]", "", compact).strip()
    if cleaned in {"/", "\\", "|"}:
        return True, "1"
    if cleaned in {"-", "—", "–", "_", ""}:
        return True, None

    # Doslowna liczba z polskim przecinkiem.
    numeric = cleaned.replace(",", ".")
    if re.fullmatch(r"\d+(?:\.\d+)?", numeric):
        return True, numeric
    return False, None


def _pick_raw_qty(item: dict, field_name: str) -> Optional[str]:
    literal_field = f"{field_name}_raw"
    if literal_field in item:
        handled, value = _decode_literal_qty(item.get(literal_field))
        if handled:
            return value

    value = item.get(field_name)
    if value is not None and value != "":
        return str(value)
    fallback = item.get("ilosc")
    if fallback is not None and fallback != "":
        return str(fallback)
    return None


_FORM_NOTES = {
    "fixed": 'poprawiono z „{raw}" na wiersz formularza — sprawdź',
    "additional": 'poprawiono z „{raw}" na pozycję spoza formularza (baza dodatkowa) — sprawdź',
    "off": "nazwa spoza formularza i bazy dodatkowej — sprawdź, czy dopasowanie poniżej jest poprawne",
}


def _plain_name(value: object) -> str:
    text = strip_diacritics(str(value or "").lower())
    text = re.sub(r"[^a-z0-9+ ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ignore_hydraulika_item(raw_name: object) -> bool:
    # Zweryfikowane koszty, ktore NIE przechodza przez Optime i nie maja trafic do receptury/TXT.
    # Reguly sa celowo bardzo waskie, zeby nie wyciac innych srub ani innych zaslepek.
    name = _plain_name(raw_name)
    return bool(
        re.fullmatch(r"sruba\s*8\s*mm", name)
        or re.fullmatch(r"zaslepka\s*127\s*czerwona", name)
    )


def _is_generic_m10_zaslepka(raw_name: object) -> bool:
    return bool(
        re.fullmatch(
            r"zaslepka\s+(?:m\s*10\s+)?(?:czarna|biala)(?:\s*\+\s*podkladka)?",
            _plain_name(raw_name),
        )
    )


def _literal_blat_name(raw_name: object) -> str | None:
    """Dla blatu z jawnym wymiarem zachowaj ostatni widoczny wymiar doslownie."""
    raw = str(raw_name or "").strip()
    if "blat kuchenny" not in _plain_name(raw):
        return None
    dims = re.findall(r"\b(\d{3,4})\s*[xX×]\s*(\d{3,4})\b", raw)
    if not dims:
        return None
    width, depth = dims[-1]
    return f"Blat kuchenny {width}x{depth}"


def _build_item_hydraulika(item: dict, catalog: Catalog, magazyn: Optional[str]) -> OCRItemHydraulika:
    raw = str(item["nazwa"]).strip()

    corrected_blat = _literal_blat_name(raw)
    if corrected_blat is not None:
        snap = snap_to_known_item_hydraulika(corrected_blat)
        # Znany poprawiony wymiar (np. 1450x600) moze wejsc normalnie. Nieznany (np. 1440x600)
        # pozostaje doslownie i ma zostac do recznej weryfikacji, bez fuzzy powrotu do starego.
        if snap.status in {"exact", "additional"}:
            recognized_name = snap.name
            snap_status = snap.status
        else:
            recognized_name = corrected_blat
            snap_status = "off"
    # "Zaslepka czarna/biala" jest zweryfikowana nazwa biznesowa, a nie kandydat do fuzzy.
    elif _is_generic_m10_zaslepka(raw):
        recognized_name = raw
        snap_status = "exact"
    else:
        snap = snap_to_known_item_hydraulika(raw)
        recognized_name = snap.name
        snap_status = snap.status

    match = match_against_catalog_hydraulika(recognized_name, catalog, magazyn=magazyn)
    if corrected_blat is not None and snap_status == "off":
        # Nieznany skorygowany wymiar ma byc BRAK DOPASOWANIA, a nie przypadkowa podpowiedz
        # do innej rodziny blatu.
        match = MatchResult(kod=None, nazwa=None, quality="bad", ratio=0.0)

    return OCRItemHydraulika(
        rozpoznana_nazwa=recognized_name,
        ilosc_wydana=_pick_raw_qty(item, "ilosc_wydana"),
        ilosc_zuzyta=_pick_raw_qty(item, "ilosc_zuzyta"),
        uwagi=str(item.get("uwagi") or ""),
        confidence=item.get("confidence"),
        needs_review=snap_status != "exact",
        off_form=snap_status == "off",
        form_note=_FORM_NOTES.get(snap_status, "").format(raw=raw) if snap_status != "exact" else "",
        match=match,
    )


async def recognize_document_hydraulika(
    files: list[tuple[bytes, str]],
    catalog: Catalog,
    magazyn: Optional[str] = None,
    chain: Optional[list[OCRChainStep]] = None,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> OCRResultHydraulika:
    try:
        context = dict(log_context or {})
        ai_stage = str(context.pop("ai_stage_override", "full_ocr_hydraulika"))
        chain_result = await run_ocr_chain(
            files, AI_OCR_PROMPT_HYDRAULIKA, chain=chain,
            response_validator=is_valid_ocr_response,
            log_context={**context, "ai_stage": ai_stage},
            event_callback=event_callback,
            cooldown_store=cooldown_store,
        )
    except AllProvidersFailedError as exc:
        if exc.last_invalid_text is not None:
            raise OCRUnparsableResponseError(exc.last_invalid_text) from exc
        raise
    parsed: Any = extract_json(chain_result.text)
    if parsed is None:
        raise OCRUnparsableResponseError(chain_result.text)

    if isinstance(parsed, list):
        raw_items, numer_projektu, pracownik, numer_plomby = parsed, None, None, None
    else:
        raw_items = parsed.get("pozycje") if isinstance(parsed.get("pozycje"), list) else []
        pn = parsed.get("numer_projektu")
        numer_projektu = normalize_project_number(str(pn).strip()) if pn else None
        pracownik = _clean_header_text(parsed.get("pracownik"))
        numer_plomby = _clean_header_text(parsed.get("numer_plomby"))

    for it in raw_items:
        if not isinstance(it, dict):
            continue
        for field in ("ilosc_wydana", "ilosc_zuzyta"):
            literal_field = f"{field}_raw"
            if literal_field not in it:
                continue
            handled, value = _decode_literal_qty(it.get(literal_field))
            if handled:
                it[field] = value

    schema_items = [it for it in raw_items if validate_item(it)]
    valid_items = [
        it for it in schema_items
        if is_actionable_item(it) and not _ignore_hydraulika_item(it.get("nazwa"))
    ]
    rejected_count = len(raw_items) - len(schema_items)

    pozycje = [_build_item_hydraulika(it, catalog, magazyn) for it in valid_items]

    return OCRResultHydraulika(
        numer_projektu=numer_projektu, pracownik=pracownik, numer_plomby=numer_plomby,
        pozycje=pozycje, used_provider=chain_result.used_label, rejected_count=rejected_count,
    )
