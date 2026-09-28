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

        alias_hit = product.kod in alias_codes

        if same_group or alias_hit:
            raw_pool.append(product)

    # Fallback: jezeli parser nie potrafil ustalic grupy,
    # ranking robimy na calym katalogu.
    if not raw_pool:
        raw_pool = list(catalog.products)

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

        previous = ranked_by_code.get(effective.kod)

        row = (
            effective,
            float(score),
            alias_hit,
        )

        if previous is None:
            ranked_by_code[effective.kod] = row
            continue

        _, previous_score, previous_alias = previous

        # Alias ma pierwszenstwo, potem podobienstwo tekstowe.
        if alias_hit and not previous_alias:
            ranked_by_code[effective.kod] = row
        elif alias_hit == previous_alias and score > previous_score:
            ranked_by_code[effective.kod] = row

    ranked = list(ranked_by_code.values())

    ranked.sort(
        key=lambda row: (
            1 if row[2] else 0,
            row[1],
        ),
        reverse=True,
    )

    ranked = ranked[:max(1, limit)]

    # Diagnostyka per-kandydat (country_match/conflict/missing, amp_*, phase_*, ...) - tylko
    # Elektryka ma dzis diagnose_candidate_elektryka(); Hydraulika dostaje None (patrz
    # docstring _query_features - to samo ograniczenie co przy cechach zapytania).
    q_elektryka = core_and_attrs(query_name) if dzial != "hydraulika" else None

    candidates = []

    for index, (product, score, is_alias) in enumerate(ranked):
        diagnostics = None
        if q_elektryka is not None:
            diagnostics = diagnose_candidate_elektryka(q_elektryka, product).as_dict()

        candidates.append(
            ShadowCandidate(
                key=f"C{index}",
                kod=product.kod,
                nazwa=product.nazwa,
                jm=product.jm,
                grupa=product.grupa,
                atrybuty=product.atrybuty or {},
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
