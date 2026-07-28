"""
Modul Matcher - port logiki matchAgainstCatalog()/bestNameMatch() z monolitu.

Zachowuje kolejnosc rozstrzygania z JS (Etap 0, pkt 2):
0) reguly specjalne dla konkretnych kodow, jako dane (special_rules.py) - wykluczenia jawne
   (np. "16/12" bez/z HI, lampa na szynoprzewod), reczne overrides tolerancyjne na OCR, przeliczniki
   (R3 szynoprzewod->zestaw, R6 grzejnik wg mocy),
1) dopasowanie po aliasach (token-containment, preferencja najbardziej specyficznego),
2) blokada grupy (pierwsze slowo core -> oczekiwana grupa),
3) konflikty atrybutow (kolor/kraj/krotnosc/prad/wymiar/przekroj/biegunowosc/moduly/srednica/montaz),
4) hierarchia tie-breaku: conflicts -> missing -> ratio,
5) generalizowana regula dominujacego kraju projektu przy prawdziwym remisie PL/DE (pokrywa tez
   stary, waski R1b dla "Gniazdo podtynkowe z klapka grafit" - patrz special_rules.py, docstring),
6) R5: podstawienie kodu wg wariantu magazynowego (jesli produkt taki ma i podano `magazyn`).
"""
from __future__ import annotations

import re
from typing import Optional

from app.modules.parser import core_and_attrs, dice_coeff
from app.modules.products.catalog import Catalog, Product, plain_tokens

from .result import MatchResult, QUALITY_OK, QUALITY_WARN, QUALITY_BAD, QUALITY_EXCLUDED
from .special_rules import DEFAULT_SPECIAL_RULES, SpecialRule, evaluate_special_rules

COLOR_TO_JSON = {
    "biały": "BIALY", "czarny": "CZARNY", "grafit": "ANTRACYT", "antracyt": "ANTRACYT",
    "szary": "SZARY", "niebieski": "NIEBIESKI", "czerwony": "CZERWONY", "żółty": "ZOLTY",
    "zielony": "ZIELONY", "transparentny": "TRANSPARENTNY",
}
COUNTRY_TO_JSON = {"PL": "PL", "DE": "DE", "FR": "FR", "EN": "UK"}

__all__ = [
    "MatchResult", "QUALITY_OK", "QUALITY_WARN", "QUALITY_BAD", "QUALITY_EXCLUDED",
    "match_against_catalog", "resolve_by_kod", "apply_warehouse_variant", "magazyn_key",
]


def _eff_color_json(cand: Product) -> str:
    return cand.atrybuty.get("kolor") or "BIALY"


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


def _alias_hits(catalog: Catalog, query_tokens: set[str]) -> list[Product]:
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


def match_against_catalog(
    query_name: str,
    catalog: Catalog,
    dominant_country: Optional[str] = None,
    magazyn: Optional[str] = None,
    special_rules: Optional[list[SpecialRule]] = None,
) -> MatchResult:
    rules = DEFAULT_SPECIAL_RULES if special_rules is None else special_rules
    special_result = evaluate_special_rules(
        query_name, rules, lambda kod: resolve_by_kod(catalog, kod, magazyn)
    )
    if special_result is not None:
        return special_result

    q = core_and_attrs(query_name)
    query_tokens = set(plain_tokens(query_name))

    alias_hits = _alias_hits(catalog, query_tokens)

    # Filtr montazu na trafienia aliasowe (ta sama asymetryczna zasada co w petli ogolnej) -
    # bez tego "Gniazdo ... NATYNKOWE" mylilo by sie z domyslnym (podtynkowym) gniazdem przez
    # alias tego drugiego, mimo poprawki w petli ogolnej ponizej.
    if q.montaz == "NATYNKOWY":
        alias_hits = [c for c in alias_hits if c.atrybuty.get("montaz") == "NATYNKOWY"]
    elif q.montaz == "PODTYNKOWY":
        alias_hits = [c for c in alias_hits if not c.atrybuty.get("montaz") or c.atrybuty.get("montaz") == "PODTYNKOWY"]

    if len(alias_hits) == 1:
        cand = apply_warehouse_variant(catalog, alias_hits[0], magazyn)
        return MatchResult(kod=cand.kod, nazwa=cand.nazwa, quality=QUALITY_OK, ratio=1.0, jm_override=cand.jm)

    q_first_word = q.core.split(" ")[0] if q.core else ""
    expected_group = catalog.first_word_group.get(q_first_word)

    search_pool = alias_hits if len(alias_hits) > 1 else catalog.products

    q_color_eff = COLOR_TO_JSON.get(q.color, "BIALY") if q.color else "BIALY"
    q_country_eff = COUNTRY_TO_JSON.get(q.country) if q.country else None
    q_krotnosc_eff = int(q.mult) if q.mult else 1  # domyslnie pojedyncze (bug wykryty 2026-07-27)

    best = None  # (conflicts, missing, ratio, cand)
    tied_best: list[tuple[int, int, float, Product]] = []

    for cand in search_pool:
        if search_pool is catalog.products and expected_group and cand.grupa != expected_group:
            continue

        ratio = dice_coeff(q.core, cand.core, cand.core_bigrams)
        conflicts = 0
        missing = 0
        a = cand.atrybuty

        if _eff_color_json(cand) != q_color_eff:
            conflicts += 1

        std = a.get("standard_gniazda")
        if q_country_eff and std:
            if q_country_eff != std:
                conflicts += 1
        elif q_country_eff and not std:
            missing += 1

        krotnosc = a.get("krotnosc")
        if krotnosc is not None and q_krotnosc_eff != krotnosc:
            conflicts += 1

        prad_a = a.get("prad_A")
        if q.amp and prad_a is not None:
            if float(q.amp) != prad_a:
                conflicts += 1
        elif q.amp and prad_a is None:
            missing += 1

        wymiar = a.get("wymiar_mm")
        if q.dim and wymiar:
            cand_dim = "x".join(sorted(str(wymiar).split("x")))
            if q.dim != cand_dim:
                conflicts += 1
        elif q.dim and not wymiar:
            missing += 1

        przekroj = a.get("przekroj_mm2")
        if q.przekroj is not None and przekroj is not None:
            if q.przekroj != przekroj:
                conflicts += 1
        elif q.przekroj is not None and przekroj is None:
            missing += 1

        zyl = a.get("liczba_zyl")
        if q.zyl is not None and zyl is not None:
            if q.zyl != zyl:
                conflicts += 1
        elif q.zyl is not None and zyl is None:
            missing += 1

        biegunow = a.get("liczba_biegunow")
        if q.biegunow is not None and biegunow is not None:
            if q.biegunow != biegunow:
                conflicts += 1
        elif q.biegunow is not None and biegunow is None:
            missing += 1

        modulow = a.get("liczba_modulow")
        if q.modulow is not None and modulow is not None:
            if q.modulow != modulow:
                conflicts += 1
        elif q.modulow is not None and modulow is None:
            missing += 1

        srednica = a.get("srednica_mm")
        if q.srednica is not None and srednica is not None:
            if q.srednica != srednica:
                conflicts += 1
        elif q.srednica is not None and srednica is None:
            missing += 1

        # Montaz - asymetryczny domysl (PODTYNKOWY = domyslny, brak informacji tez ok)
        cand_montaz = a.get("montaz")
        if q.montaz == "NATYNKOWY":
            if cand_montaz != "NATYNKOWY":
                conflicts += 1
        elif q.montaz == "PODTYNKOWY" and cand_montaz and cand_montaz != "PODTYNKOWY":
            conflicts += 1

        phase_penalty = 0
        if q.phase and cand.phase:
            if q.phase != cand.phase:
                phase_penalty = 100
        elif q.phase and not cand.phase:
            missing += 1

        total_conflicts = conflicts + phase_penalty
        score = (total_conflicts, missing, ratio, cand)

        if best is None:
            best = score
            tied_best = [score]
            continue
        if total_conflicts < best[0]:
            best = score
            tied_best = [score]
            continue
        if total_conflicts == best[0]:
            if missing < best[1]:
                best = score
                tied_best = [score]
            elif missing == best[1]:
                if ratio > best[2]:
                    best = score
                    tied_best = [score]
                elif ratio == best[2]:
                    tied_best.append(score)

    if best is None:
        return MatchResult(kod=None, nazwa=None, quality=QUALITY_BAD, ratio=0.0)

    # Generalizowana regula dominujacego kraju (R1b uogolnione, bug wykryty 2026-07-27):
    # gdy prawdziwy remis rozniący sie WYLACZNIE krajem, a zapytanie nie podalo kraju wprost,
    # rozstrzygamy dominujacym standardem calego projektu zamiast kolejnoscia w katalogu.
    if len(tied_best) > 1 and not q_country_eff:
        countries = {s[3].atrybuty.get("standard_gniazda") for s in tied_best if s[3].atrybuty.get("standard_gniazda")}
        if len(countries) >= 2:
            country = dominant_country or "PL"
            pick = next((s for s in tied_best if s[3].atrybuty.get("standard_gniazda") == country), None)
            pick = pick or next((s for s in tied_best if s[3].atrybuty.get("standard_gniazda") == "PL"), None)
            best = pick or tied_best[0]

    conflicts, missing, ratio, cand = best
    phase_ok = not (q.phase and cand.phase and q.phase != cand.phase)
    ok = conflicts == 0 and ratio >= 0.55 and phase_ok
    warn = conflicts == 0 and ratio >= 0.40 and phase_ok
    quality = QUALITY_OK if ok else (QUALITY_WARN if warn else QUALITY_BAD)

    final_cand = apply_warehouse_variant(catalog, cand, magazyn)
    return MatchResult(kod=final_cand.kod, nazwa=final_cand.nazwa, quality=quality, ratio=ratio, jm_override=final_cand.jm)
