"""Niezalezna warstwa Jev Shadow dla Multiplexera.

Zasady:
- obecny matcher nadal podejmuje prawdziwa decyzje,
- Jev nie zna decyzji matchera podczas swojej oceny,
- Jev dostaje tylko sensowna shortliste produktow, wraz z jawnie sparsowanymi cechami
  zapytania i strukturalna diagnostyka zgodnosci per-kandydat (country/amp/phase/...),
- wynik Jev nie zmienia kodu produktu ani eksportu TXT,
- wynik sluzy tylko do porownania MATCHER vs JEV,
- KAZDY blad komunikacji z Jev jest fail-open: zwracamy None, stary Multiplekser
  dziala dalej normalnie (patrz evaluate_shadow, blok try/except wokol ask_choice).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from app.modules.matcher.candidate_diagnostics import diagnose_candidate_elektryka
from app.modules.matcher.result import MatchResult
from app.modules.matcher.shared import alias_hits, apply_warehouse_variant
from app.modules.parser import (
    core_and_attrs,
    core_and_attrs_hydraulika,
    dice_coeff,
)
from app.modules.products import Catalog
from app.modules.products.catalog import plain_tokens

from .jev_client import JevError, ask_choice, jev_enabled, jev_mode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ShadowCandidate:
    key: str
    kod: str
    nazwa: str
    jm: str
    grupa: str
    atrybuty: dict
    score: float
    alias_hit: bool
    current_match: bool
    diagnostics: Optional[dict] = None


@dataclass(frozen=True)
class JevShadowResult:
    matcher_kod: Optional[str]
    jev_kod: Optional[str]
    agrees: bool
    matcher_in_shortlist: bool
    confidence: float
    probabilities: dict[str, float]
    model: str
    candidates: list[ShadowCandidate]
    query_features: dict
    input_tokens: int
    output_tokens: int


def _query_core(query_name: str, dzial: str) -> str:
    if dzial == "hydraulika":
        return core_and_attrs_hydraulika(query_name).core

    return core_and_attrs(query_name).core


def _query_features(query_name: str, dzial: str) -> dict:
    """Jawnie sparsowane cechy zapytania (Etap 3) - te same, ktore widzi matcher, ale
    tutaj przekazywane Jev wprost, zamiast liczyc na to, ze wywnioskuje je z surowego tekstu.
    Tylko Elektryka ma dzis pelny zestaw pol (phase/amp/dim/...) - Hydraulika dostaje core."""
    if dzial == "hydraulika":
        parsed = core_and_attrs_hydraulika(query_name)
        return {"raw": query_name, "core": parsed.core}

    parsed = core_and_attrs(query_name)
    return {
        "raw": query_name,
        "core": parsed.core,
        "country": parsed.country,
        "amp": parsed.amp,
        "phase": parsed.phase,
        "dim": parsed.dim,
        "color": parsed.color,
        "zyl": parsed.zyl,
        "przekroj": parsed.przekroj,
        "srednica": parsed.srednica,
        "biegunow": parsed.biegunow,
        "modulow": parsed.modulow,
        "montaz": parsed.montaz,
    }


def _compact_attrs(attrs: dict) -> dict:
    """Tylko atrybuty przydatne Jev; bez technicznego _meta i pustych pol."""
    out = {}
    for key, value in (attrs or {}).items():
        if key.startswith("_"):
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue
        out[key] = value
    return out


def _same_product_family(query_core: str, product_core: str) -> bool:
    """Lekki filtr rodziny produktu przed rankingiem Jev.

    Grupy Optimy sa szerokie (np. Aparatura modulowa), wiec sama grupa potrafi
    wrzucic do shortlisty roznicznik przy zapytaniu o roznicowke. Porownujemy
    pierwszy rdzen nazwy; tolerujemy typowe odmiany/ucięcia OCR przez wspolny
    prefiks co najmniej 5 znakow.
    """
    q_first = query_core.split(" ")[0] if query_core else ""
    p_first = product_core.split(" ")[0] if product_core else ""
    if not q_first or not p_first:
        return False
    if q_first == p_first:
        return True
    common = 0
    for q_char, p_char in zip(q_first, p_first):
        if q_char != p_char:
            break
        common += 1
    return common >= 5


def _diagnostic_rank(diagnostics: Optional[dict]) -> tuple[int, int, int]:
    """Ranking diagnostyczny bez wiedzy o wyniku matchera.

    Najpierw odrzucamy kandydatow z konfliktami atrybutow, potem premiujemy
    zgodne atrybuty i na koncu mniej brakujacych danych. Zwracane wartosci
    sa przygotowane pod sortowanie reverse=True.
    """
    if not diagnostics:
        return (0, 0, 0)

    conflicts = sum(
        1 for key, value in diagnostics.items()
        if key.endswith("_conflict") and bool(value)
    )
    matches = sum(
        1 for key, value in diagnostics.items()
        if key.endswith("_match") and key != "color_match" and bool(value)
    )
    missing = sum(
        1 for key, value in diagnostics.items()
        if key.endswith("_missing") and bool(value)
    )
    return (-conflicts, matches, -missing)


def build_shortlist(
    *,
    query_name: str,
    catalog: Catalog,
    current_match: MatchResult,
    dzial: str,
    magazyn: Optional[str] = None,
    limit: int = 5,
) -> list[ShadowCandidate]:
    """Buduje shortliste niezaleznie od decyzji obecnego matchera."""

    query_core = _query_core(query_name, dzial)
    query_tokens = set(plain_tokens(query_name))

    first_word = query_core.split(" ")[0] if query_core else ""
    expected_group = catalog.first_word_group.get(first_word)

    aliases = alias_hits(catalog, query_tokens)
    alias_codes = {product.kod for product in aliases}

    # Kandydaci:
    # 1. produkty z grupy wynikajacej z tekstu OCR,
    # 2. produkty trafione przez alias.
    #
    # Nie dodajemy produktu tylko dlatego, ze wybral go matcher.
    raw_pool = []

    for product in catalog.products:
        same_group = (
            expected_group is not None
            and product.grupa == expected_group
        )
        same_family = _same_product_family(query_core, product.core)

        alias_hit = product.kod in alias_codes

        if (same_group and same_family) or alias_hit:
            raw_pool.append(product)

    # Fallback: gdy OCR jest zbyt znieksztalcony, wracamy do szerszej grupy,
    # a dopiero gdy nawet jej nie znamy - do calego katalogu.
    if not raw_pool and expected_group is not None:
        raw_pool = [p for p in catalog.products if p.grupa == expected_group]
    if not raw_pool:
        raw_pool = list(catalog.products)

    q_elektryka = core_and_attrs(query_name) if dzial != "hydraulika" else None

    ranked_by_code = {}

    for product in raw_pool:
        effective = apply_warehouse_variant(
            catalog,
            product,
            magazyn,
        )

        score = dice_coeff(
            query_core,
            product.core,
            product.core_bigrams,
        )

        alias_hit = product.kod in alias_codes

        diagnostics = None
        if q_elektryka is not None:
            diagnostics = diagnose_candidate_elektryka(
                q_elektryka,
                effective,
            ).as_dict()

        previous = ranked_by_code.get(effective.kod)

        row = (
            effective,
            float(score),
            alias_hit,
            diagnostics,
        )

        if previous is None:
            ranked_by_code[effective.kod] = row
            continue

        _, previous_score, previous_alias, previous_diagnostics = previous
        row_rank = (
            1 if alias_hit else 0,
            *_diagnostic_rank(diagnostics),
            float(score),
        )
        previous_rank = (
            1 if previous_alias else 0,
            *_diagnostic_rank(previous_diagnostics),
            float(previous_score),
        )
        if row_rank > previous_rank:
            ranked_by_code[effective.kod] = row

    ranked = list(ranked_by_code.values())

    ranked.sort(
        key=lambda row: (
            1 if row[2] else 0,
            *_diagnostic_rank(row[3]),
            row[1],
        ),
        reverse=True,
    )

    ranked = ranked[:max(1, limit)]

    candidates = []

    for index, (product, score, is_alias, diagnostics) in enumerate(ranked):

        candidates.append(
            ShadowCandidate(
                key=f"C{index}",
                kod=product.kod,
                nazwa=product.nazwa,
                jm=product.jm,
                grupa=product.grupa,
                atrybuty=_compact_attrs(product.atrybuty or {}),
                score=score,
                alias_hit=is_alias,
                current_match=(
                    product.kod == current_match.kod
                ),
                diagnostics=diagnostics,
            )
        )

    return candidates


async def evaluate_shadow(
    *,
    query_name: str,
    catalog: Catalog,
    current_match: MatchResult,
    dzial: str,
    magazyn: Optional[str] = None,
    limit: int = 5,
) -> Optional[JevShadowResult]:
    """Niezalezna ocena kandydatow przez Jev.

    Fail-open: KAZDY blad komunikacji z TypeSafe (timeout, siec, HTTP != 200, niepoprawna
    odpowiedz) jest tutaj zlapany i zwraca None - nigdy nie wysadza przetwarzania dokumentu.
    Rowniez brak/niedostepnosc modulu (jev_enabled()==False lub tryb inny niz shadow) -> None."""

    if not jev_enabled():
        return None

    if jev_mode() != "shadow":
        return None

    try:
        candidates = build_shortlist(
            query_name=query_name,
            catalog=catalog,
            current_match=current_match,
            dzial=dzial,
            magazyn=magazyn,
            limit=limit,
        )

        if not candidates:
            return None

        query_features = _query_features(query_name, dzial)

        key_to_code = {
            candidate.key: candidate.kod
            for candidate in candidates
        }

        state_candidates = []
        criteria = {}

        for candidate in candidates:
            attrs_text = json.dumps(
                candidate.atrybuty,
                ensure_ascii=False,
                sort_keys=True,
            )

            state_candidates.append(
                {
                    "id": candidate.key,
                    "kod": candidate.kod,
                    "nazwa": candidate.nazwa,
                    "jm": candidate.jm,
                    "grupa": candidate.grupa,
                    "atrybuty": candidate.atrybuty,
                    "score": candidate.score,
                    "diagnostics": candidate.diagnostics,
                }
            )

            diag_text = ""
            if candidate.diagnostics:
                signals = [k for k, v in candidate.diagnostics.items() if v]
                if signals:
                    diag_text = f"; Diagnostyka: {', '.join(signals)}"

            criteria[candidate.key] = (
                f"Kod: {candidate.kod}; "
                f"Nazwa: {candidate.nazwa}; "
                f"Grupa: {candidate.grupa}; "
                f"JM: {candidate.jm}; "
                f"Atrybuty: {attrs_text}"
                f"{diag_text}"
            )

        criteria["OTHER"] = (
            "Zaden z przedstawionych produktow nie odpowiada "
            "pozycji rozpoznanej przez OCR."
        )

        # UWAGA:
        # current_match celowo NIE znajduje sie w state ani instructions.
        # Jev ma podjac decyzje niezaleznie od starego matchera.
        result = await ask_choice(
            state={
                "ocr_text": query_name,
                "dzial": dzial,
                "magazyn": magazyn,
                "query_features": query_features,
                "candidates": state_candidates,
            },
            question_name="produkt",
            instructions=(
                "Wybierz produkt najlepiej odpowiadajacy pozycji "
                "rozpoznanej przez OCR z magazynowej wydawki. "
                "Uwzglednij znaczenie nazwy, parametry techniczne, "
                "wariant, kraj, wymiar, kolor, prad, fazy, srednice "
                "i inne dostepne atrybuty, oraz pole 'diagnostics' przy "
                "kazdym kandydacie (opisuje zgodnosc/konflikt/brak danych "
                "per atrybut wzgledem query_features). "
                "Nie wybieraj produktu tylko na podstawie podobienstwa "
                "tekstu. Jezeli zaden kandydat nie pasuje, wybierz OTHER."
            ),
            criteria=criteria,
        )
    except JevError as exc:
        logger.warning("Jev shadow - blad TypeSafe, pomijam (fail-open)", exc_info=exc)
        return None
    except Exception:  # zabezpieczenie - Jev NIGDY nie moze wysadzic przetwarzania dokumentu
        logger.warning("Jev shadow - nieoczekiwany blad, pomijam (fail-open)", exc_info=True)
        return None

    jev_kod = key_to_code.get(result.choice)

    matcher_in_shortlist = any(
        candidate.kod == current_match.kod
        for candidate in candidates
    )

    agrees = bool(
        current_match.kod
        and jev_kod
        and current_match.kod == jev_kod
    )

    return JevShadowResult(
        matcher_kod=current_match.kod,
        jev_kod=jev_kod,
        agrees=agrees,
        matcher_in_shortlist=matcher_in_shortlist,
        confidence=result.confidence,
        probabilities=result.probabilities,
        model=result.model,
        candidates=candidates,
        query_features=query_features,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
