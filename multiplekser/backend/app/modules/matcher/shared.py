"""Dolna warstwa Matchera - naprawde wspolna miedzy dzialami, wydzielona z dawnego core.py
(patrz docs/RAPORT_NAZEWNICTWO_1.md). Uzywana wprost przez oba `match_against_catalog*`
(core_elektryka.py/core_hydraulika.py) i przez router dokumentow (magazyn - Krok Hydraulika-6).

Zero logiki specyficznej dla ktoregokolwiek dzialu - operuje wylacznie na Catalog/Product/tekst,
nie na nazwach atrybutow (te sa fundamentalnie inne miedzy dzialami, patrz core_hydraulika.py)."""
from __future__ import annotations

import re
from typing import Optional

from app.modules.products.catalog import Catalog, Product

from .result import MatchResult, QUALITY_BAD, QUALITY_OK


def magazyn_key(magazyn: Optional[str]) -> Optional[str]:
    """R5: normalizacja nazwy magazynu do klucza uzywanego w warianty_magazynowe (case-insensitive)."""
    if not magazyn:
        return None
    if re.search(r"czekan", magazyn, re.I):
        return "Czekanów"
    if re.search(r"zabrze", magazyn, re.I):
        return "Zabrze"
    return None


def apply_warehouse_variant(catalog: Catalog, cand: Product, magazyn: Optional[str]) -> Product:
    """R5: ten sam towar, inny kod w Optimie w zaleznosci od wybranego magazynu."""
    if not cand or not cand.warianty_magazynowe:
        return cand
    key = magazyn_key(magazyn)
    if not key:
        return cand
    substitute_kod = cand.warianty_magazynowe.get(key)
    if not substitute_kod or substitute_kod == cand.kod:
        return cand
    substitute = catalog.find_by_kod(substitute_kod)
    return substitute or cand


def resolve_by_kod(catalog: Catalog, kod: Optional[str], magazyn: Optional[str] = None) -> MatchResult:
    cand = catalog.find_by_kod(kod) if kod else None
    if not cand:
        return MatchResult(kod=None, nazwa=None, quality=QUALITY_BAD, ratio=0.0)
    cand = apply_warehouse_variant(catalog, cand, magazyn)
    return MatchResult(kod=cand.kod, nazwa=cand.nazwa, quality=QUALITY_OK, ratio=1.0, jm_override=cand.jm)


def alias_hits(catalog: Catalog, query_tokens: set[str]) -> list[Product]:
    """Zwraca produkty, ktorych NAJBARDZIEJ SPECYFICZNY pasujacy alias ma najwiecej tokenow -
    zapobiega sytuacji gdzie krotszy (mniej precyzyjny) alias przypadkowo wygrywa remis."""
    raw: list[tuple[Product, int]] = []
    for cand in catalog.products:
        best_len = 0
        matched = False
        for alias in cand.aliasy:
            if len(alias.tokens) < 2:
                continue  # aliasy szumowe (np. samo "CZARNY") sa ignorowane
            if all(t in query_tokens for t in alias.tokens):
                matched = True
                best_len = max(best_len, len(alias.tokens))
        if matched:
            raw.append((cand, best_len))
    if not raw:
        return []
    max_spec = max(spec for _, spec in raw)
    return [c for c, spec in raw if spec == max_spec]
