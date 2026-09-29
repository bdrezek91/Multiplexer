"""Aktywny tryb Jev dla Elektryki.

Gemini wykonuje OCR, obecny matcher buduje bazowe dopasowanie, a Jev moze wybrac finalny kod.
Reguly specjalne maja zawsze pierwszenstwo. Blad TypeSafe zostawia stary matcher. OTHER zostawia dobry/warn matcher, ale usuwa slabe dopasowanie i wymusza reczna weryfikacje.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from app.modules.matcher.result import MatchResult, QUALITY_BAD, QUALITY_OK
from app.modules.matcher.shared import apply_warehouse_variant, resolve_by_kod
from app.modules.matcher.special_rules import SpecialRule, evaluate_special_rules, find_matching_special_rule
from app.modules.parser import core_and_attrs
from app.modules.products import Catalog

from .jev_client import jev_enabled, jev_mode
from .jev_shadow import evaluate_shadow

logger = logging.getLogger(__name__)


def _effective_poles_from_query(query_name: str) -> int:
    """Konwencja DAMPOL: brak xP na wydawce oznacza 1P."""
    parsed = core_and_attrs(query_name)
    return int(parsed.biegunow) if parsed.biegunow is not None else 1


def _candidate_poles(candidate) -> int | None:
    raw = (candidate.atrybuty or {}).get("liczba_biegunow")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass
    parsed = core_and_attrs(candidate.nazwa)
    return int(parsed.biegunow) if parsed.biegunow is not None else None


def _candidate_respects_poles(query_name: str, candidate) -> bool:
    cand_poles = _candidate_poles(candidate)
    if cand_poles is None:
        return True
    return cand_poles == _effective_poles_from_query(query_name)


def _is_weak_match(match: MatchResult) -> bool:
    return match.quality == QUALITY_BAD or float(match.ratio or 0.0) < 0.40


def _append_review_note(item: dict, text: str) -> None:
    existing = str(item.get("form_note") or "").strip()
    if text in existing:
        return
    item["form_note"] = f"{existing} | {text}" if existing else text


async def apply_jev_active(
    *,
    items: list[dict],
    catalog: Catalog,
    special_rules: list[SpecialRule],
    magazyn: Optional[str],
    dzial: str,
    resolve_product_id: Callable[[str], object | None],
) -> list[dict]:
    if not jev_enabled() or jev_mode() != "active" or dzial != "elektryka":
        return []

    jobs = []
    meta = []
    for sequence, item in enumerate(items):
        name = str(item.get("rozpoznana_nazwa") or "").strip()
        if not name:
            continue
        current_match = MatchResult(
            kod=item.get("match_kod"),
            nazwa=item.get("match_nazwa"),
            quality=item.get("match_quality") or "bad",
            ratio=float(item.get("match_score") or 0.0),
            jm_override=item.get("match_jm"),
        )
        matched_rule = find_matching_special_rule(name, special_rules)
        special_result = evaluate_special_rules(
            name,
            special_rules,
            lambda kod: resolve_by_kod(catalog, kod, magazyn),
        )
        # Pozycje dodane automatycznie przez nasze istniejace reguly (np. zasilacz
        # do tasmy LED) sa tak samo chronione jak special rules - Jev moze je ocenic, ale nie
        # moze zmienic kodu ustalonego przez logike biznesowa.
        auto_generated = str(item.get("form_note") or "").startswith("Dodano automatycznie")
        locked = special_result is not None or auto_generated

        rule_context = None
        if matched_rule is not None:
            rule_context = {
                "authoritative": True,
                "kind": "special_rule",
                "rule_type": matched_rule.rule_type,
                "description": matched_rule.description,
                "target_kod": special_result.kod if special_result is not None else matched_rule.target_kod,
            }
        elif auto_generated:
            rule_context = {
                "authoritative": True,
                "kind": "auto_generated",
                "description": item.get("form_note"),
                "target_kod": current_match.kod,
            }

        meta.append((sequence, item, current_match, locked))
        jobs.append(evaluate_shadow(
            query_name=name,
            catalog=catalog,
            current_match=current_match,
            dzial=dzial,
            magazyn=magazyn,
            business_rule_context=rule_context,
        ))

    if not jobs:
        return []

    results = await asyncio.gather(*jobs, return_exceptions=True)
    out: list[dict] = []
    for (sequence, item, current_match, locked), result in zip(meta, results):
        if isinstance(result, BaseException):
            logger.warning("Jev active - wyjatek, zostawiam matcher", exc_info=result)
            continue
        if result is None:
            continue

        applied = False
        cleared_weak_match = False
        rejected_by_poles = False

        if not locked and result.jev_kod:
            candidate = catalog.find_by_kod(result.jev_kod)
            if candidate is not None:
                candidate = apply_warehouse_variant(catalog, candidate, magazyn)

                # Twarda konwencja DAMPOL: brak xP na wydawce = 1P.
                # Jev nie moze sam dopowiedziec 3P. Nawet jesli TypeSafe wybierze taki kod,
                # zostawiamy bezpieczny wynik matchera.
                if not _candidate_respects_poles(
                    str(item.get("rozpoznana_nazwa") or ""),
                    candidate,
                ):
                    rejected_by_poles = True
                else:
                    item["match_kod"] = candidate.kod
                    item["match_nazwa"] = candidate.nazwa
                    item["match_jm"] = candidate.jm
                    item["matched_product_id"] = resolve_product_id(candidate.kod)
                    item["match_quality"] = QUALITY_OK
                    item["match_score"] = float(result.confidence)
                    applied = candidate.kod != current_match.kod

        # Jev OTHER + slaby matcher = nie eksportujemy przypadkowego kodu.
        # Dla dobrego/warn matchera nadal obowiazuje fail-open i zostawiamy stary wynik.
        elif not locked and result.jev_kod is None and _is_weak_match(current_match):
            item["match_kod"] = None
            item["match_nazwa"] = None
            item["match_jm"] = None
            item["matched_product_id"] = None
            item["match_quality"] = QUALITY_BAD
            item["match_score"] = 0.0
            item["needs_review"] = True
            _append_review_note(
                item,
                "Jev: brak pewnego dopasowania (OTHER), a matcher był słaby — zweryfikuj ręcznie.",
            )
            cleared_weak_match = True

        out.append({
            "sequence": sequence,
            "rozpoznana_nazwa": item.get("rozpoznana_nazwa"),
            "matcher_kod": result.matcher_kod,
            "jev_kod": result.jev_kod,
            "agrees": result.agrees,
            "matcher_in_shortlist": result.matcher_in_shortlist,
            "confidence": result.confidence,
            "model": result.model,
            "probabilities": result.probabilities,
            "query_features": {
                **result.query_features,
                "active_applied": applied,
                "active_locked_by_special_rule": locked,
                "active_cleared_weak_match": cleared_weak_match,
                "active_rejected_by_poles": rejected_by_poles,
            },
            "candidate_codes": [c.kod for c in result.candidates],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_ms": result.duration_ms,
            "applied": applied,
            "locked_by_special_rule": locked,
        })

    return out
