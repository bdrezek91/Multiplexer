"""Pipeline OCR: lancuch dostawcow -> parsowanie -> walidacja -> dopasowanie do katalogu.

Port glownej czesci runAI() z monolitu (bez fragmentow UI/DOM). Celowo NIE zawiera:
- pickQty/qtySource (wybor "ktora ilosc pokazac") - to decyzja przy generowaniu, nie przy
  odczycie; endpoint zwraca obie kolumny (ilosc_wydana/ilosc_zuzyta) osobno, tak jak przeczytal je AI,
- dominantCountry przy dopasowaniu - w monolicie bestNameMatch() podczas OCR TEZ jest wolane bez
  trzeciego argumentu (dominujacy kraj liczony jest dopiero z calego dokumentu przy generowaniu,
  w generateOutput() - modul Generator, jeszcze nie przeniesiony). Zachowane 1:1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from app.modules.matcher import MatchResult, match_against_catalog
from app.modules.matcher.special_rules import SpecialRule
from app.modules.products import Catalog

from .chain import OCRChainStep, run_ocr_chain
from .form_rows_elektryka import reconcile_form_row, snap_to_form_row
from .parsing import extract_json, validate_item
from .prompt import AI_OCR_PROMPT


def normalize_project_number(text: str) -> str:
    """Port normalizeProjectNumber() - np. '35/06/26' -> '35/06/2026'."""
    normalized = re.sub(r"[_\-\s.]+", "/", text)
    parts = normalized.split("/")
    if len(parts) == 3:
        year = parts[2]
        if len(year) == 2:
            y = int(year)
            year = ("20" if 0 <= y <= 30 else "19") + year
        parts[2] = year
        return "/".join(parts)
    return normalized


class OCRUnparsableResponseError(Exception):
    """AI zwrocilo tekst, z ktorego nie da sie wyciagnac JSON (port komunikatu z runAI())."""

    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        fragment = re.sub(r"\s+", " ", raw_text or "(pusta odpowiedź)").strip()[:180]
        super().__init__(f"AI zwróciło nie-JSON. Odpowiedź modelu: „{fragment}…”")


@dataclass
class OCRItem:
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
class OCRResult:
    numer_projektu: Optional[str]
    pozycje: list[OCRItem]
    used_provider: str
    rejected_count: int


def _pick_raw_qty(item: dict, field_name: str) -> Optional[str]:
    """Kompatybilnosc wstecz (jak w monolicie): jesli model mimo nowego promptu zwroci stare,
    pojedyncze pole 'ilosc', traktujemy je jako obie kolumny (wydana/zuzyta) rownoczesnie."""
    value = item.get(field_name)
    if value is not None and value != "":
        return str(value)
    fallback = item.get("ilosc")
    if fallback is not None and fallback != "":
        return str(fallback)
    return None


def _build_item(
    item: dict, catalog: Catalog, special_rules: list[SpecialRule], magazyn: Optional[str],
) -> OCRItem:
    raw = str(item["nazwa"]).strip()
    snap = snap_to_form_row(raw)
    reconciled = reconcile_form_row(raw, snap)

    match = match_against_catalog(reconciled.nazwa, catalog, magazyn=magazyn, special_rules=special_rules)
    # Bug-fix z monolitu (2026-07-27): dla dopiskow niepewnego pochodzenia (off_form) samo
    # podobienstwo tekstu ponizej 0.70 jest czesto przypadkowym nakladaniem sie ogolnych slow,
    # nie realnym dopasowaniem - degradujemy quality 'ok' do 'bad' zamiast po cichu zasilic zly kod.
    if reconciled.uncertain and match.quality == "ok" and match.ratio < 0.70:
        match = MatchResult(kod=match.kod, nazwa=match.nazwa, quality="bad", ratio=match.ratio, jm_override=match.jm_override)

    return OCRItem(
        rozpoznana_nazwa=reconciled.nazwa,
        ilosc_wydana=_pick_raw_qty(item, "ilosc_wydana"),
        ilosc_zuzyta=_pick_raw_qty(item, "ilosc_zuzyta"),
        uwagi=str(item.get("uwagi") or ""),
        confidence=item.get("confidence"),
        needs_review=snap.status != "exact",
        off_form=reconciled.uncertain,
        form_note=reconciled.form_note,
        match=match,
    )


async def recognize_document(
    file_bytes: bytes,
    mime: str,
    catalog: Catalog,
    special_rules: list[SpecialRule],
    magazyn: Optional[str] = None,
    chain: Optional[list[OCRChainStep]] = None,
) -> OCRResult:
    chain_result = await run_ocr_chain(file_bytes, mime, AI_OCR_PROMPT, chain=chain)
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

    pozycje = [_build_item(it, catalog, special_rules, magazyn) for it in valid_items]

    return OCRResult(
        numer_projektu=numer_projektu, pozycje=pozycje,
        used_provider=chain_result.used_label, rejected_count=rejected_count,
    )
