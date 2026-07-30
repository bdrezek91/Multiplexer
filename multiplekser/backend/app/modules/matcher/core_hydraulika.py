"""Odpowiednik match_against_catalog() (core_elektryka.py) dla dzialu Hydraulika - OSOBNA
funkcja, nie wspolny silnik generyczny (swiadoma decyzja, ta sama co w parser/hydraulika.py:
zestaw atrybutow jest fundamentalnie inny - gwint/material/zlacze zamiast kraj/kolor/montaz/faza
- wspolny silnik konfiguracji per dzial (AttributeRule) byl rozwazany i odrzucony na rzecz
zachowania tego samego stylu co juz istniejacy special_rules.py, patrz CLAUDE.md).

Wspolna warstwa: resolve_by_kod/apply_warehouse_variant/alias_hits/dice_coeff/MatchResult -
wszystkie juz dzial-agnostyczne (operuja na Catalog/Product/tekst, nie na nazwach atrybutow),
w matcher/shared.py."""
from __future__ import annotations

from typing import Optional

from app.modules.parser import core_and_attrs_hydraulika, dice_coeff
from app.modules.products.catalog import Catalog, Product, plain_tokens

from .result import MatchResult, QUALITY_OK, QUALITY_WARN, QUALITY_BAD
from .shared import alias_hits, apply_warehouse_variant, resolve_by_kod
from .special_rules import SpecialRule, evaluate_special_rules

# Domyslnie brak regul specjalnych dla Hydrauliki - MANUAL_OVERRIDES/WAREHOUSE_OVERRIDES byly
# swiadomie puste juz w oryginalnej analizie katalogu (patrz docs/MIGRATION_PLAN_HYDRAULIKA.md,
# tabela w sekcji 2). Ten sam mechanizm co special_rules.py (Elektryka) - gotowy punkt
# rozszerzenia, gdy pojawi sie pierwszy realny wyjatek do obsluzenia.
DEFAULT_SPECIAL_RULES_HYDRAULIKA: list[SpecialRule] = []


def match_against_catalog_hydraulika(
    query_name: str,
    catalog: Catalog,
    magazyn: Optional[str] = None,
    special_rules: Optional[list[SpecialRule]] = None,
) -> MatchResult:
    rules = DEFAULT_SPECIAL_RULES_HYDRAULIKA if special_rules is None else special_rules
    special_result = evaluate_special_rules(
        query_name, rules, lambda kod: resolve_by_kod(catalog, kod, magazyn)
    )
    if special_result is not None:
        return special_result

    q = core_and_attrs_hydraulika(query_name)
    query_tokens = set(plain_tokens(query_name))

    hits = alias_hits(catalog, query_tokens)
    if len(hits) == 1:
        cand = apply_warehouse_variant(catalog, hits[0], magazyn)
        return MatchResult(kod=cand.kod, nazwa=cand.nazwa, quality=QUALITY_OK, ratio=1.0, jm_override=cand.jm)

    q_first_word = q.core.split(" ")[0] if q.core else ""
    expected_group = catalog.first_word_group.get(q_first_word)

    search_pool = hits if len(hits) > 1 else catalog.products

    q_kolor_eff = q.kolor or "BIALY"

    best = None  # (conflicts, missing, ratio, cand)
    tied_best: list[tuple[int, int, float, Product]] = []

    for cand in search_pool:
        if search_pool is catalog.products and expected_group and cand.grupa != expected_group:
            continue

        ratio = dice_coeff(q.core, cand.core, cand.core_bigrams)
        conflicts = 0
        missing = 0
        a = cand.atrybuty

        cand_kolor_eff = a.get("kolor") or "BIALY"
        if cand_kolor_eff != q_kolor_eff:
            conflicts += 1

        for query_val, product_field, caster in (
            (q.srednica_mm, "srednica_mm", float),
            (q.gwint_cal, "gwint_cal", None),
            (q.material, "material", None),
            (q.zlacze, "zlacze", None),
            (q.kat_st, "kat_st", int),
            (q.dlugosc_cm, "dlugosc_cm", int),
            (q.pojemnosc_l, "pojemnosc_l", int),
        ):
            cand_val = a.get(product_field)
            if query_val is None:
                continue
            if cand_val is None:
                missing += 1
                continue
            eff_val = caster(cand_val) if caster else cand_val
            if query_val != eff_val:
                conflicts += 1

        score = (conflicts, missing, ratio, cand)

        if best is None:
            best = score
            tied_best = [score]
            continue
        if conflicts < best[0]:
            best = score
            tied_best = [score]
            continue
        if conflicts == best[0]:
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

    conflicts, missing, ratio, cand = best
    ok = conflicts == 0 and ratio >= 0.55
    warn = conflicts == 0 and ratio >= 0.40
    quality = QUALITY_OK if ok else (QUALITY_WARN if warn else QUALITY_BAD)

    final_cand = apply_warehouse_variant(catalog, cand, magazyn)
    return MatchResult(kod=final_cand.kod, nazwa=final_cand.nazwa, quality=quality, ratio=ratio, jm_override=final_cand.jm)
