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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.modules.matcher import MatchResult, match_against_catalog_hydraulika
from app.modules.products import Catalog

from .chain import OCRChainStep, run_ocr_chain
from .form_rows_hydraulika import snap_to_known_item_hydraulika
from .parsing import extract_json, validate_item
from .pipeline_elektryka import OCRUnparsableResponseError, normalize_project_number
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
    pozycje: list[OCRItemHydraulika]
    used_provider: str
    rejected_count: int


def _pick_raw_qty(item: dict, field_name: str) -> Optional[str]:
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


def _build_item_hydraulika(item: dict, catalog: Catalog, magazyn: Optional[str]) -> OCRItemHydraulika:
    raw = str(item["nazwa"]).strip()
    snap = snap_to_known_item_hydraulika(raw)

    match = match_against_catalog_hydraulika(snap.name, catalog, magazyn=magazyn)

    return OCRItemHydraulika(
        rozpoznana_nazwa=snap.name,
        ilosc_wydana=_pick_raw_qty(item, "ilosc_wydana"),
        ilosc_zuzyta=_pick_raw_qty(item, "ilosc_zuzyta"),
        uwagi=str(item.get("uwagi") or ""),
        confidence=item.get("confidence"),
        needs_review=snap.status != "exact",
        off_form=snap.status == "off",
        form_note=_FORM_NOTES.get(snap.status, "").format(raw=raw) if snap.status != "exact" else "",
        match=match,
    )


async def recognize_document_hydraulika(
    file_bytes: bytes,
    mime: str,
    catalog: Catalog,
    magazyn: Optional[str] = None,
    chain: Optional[list[OCRChainStep]] = None,
) -> OCRResultHydraulika:
    chain_result = await run_ocr_chain(file_bytes, mime, AI_OCR_PROMPT_HYDRAULIKA, chain=chain)
    parsed: Any = extract_json(chain_result.text)
    if parsed is None:
        raise OCRUnparsableResponseError(chain_result.text)

    if isinstance(parsed, list):
        raw_items, numer_projektu = parsed, None
    else:
        raw_items = parsed.get("pozycje") if isinstance(parsed.get("pozycje"), list) else []
        pn = parsed.get("numer_projektu")
        numer_projektu = normalize_project_number(str(pn).strip()) if pn else None

    valid_items = [it for it in raw_items if validate_item(it)]
    rejected_count = len(raw_items) - len(valid_items)

    pozycje = [_build_item_hydraulika(it, catalog, magazyn) for it in valid_items]

    return OCRResultHydraulika(
        numer_projektu=numer_projektu, pozycje=pozycje,
        used_provider=chain_result.used_label, rejected_count=rejected_count,
    )
