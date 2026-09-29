"""Aktywny tryb Jev dla Elektryki.

Gemini wykonuje OCR, obecny matcher buduje bazowe dopasowanie, a Jev moze wybrac finalny kod.
Reguly specjalne maja zawsze pierwszenstwo. Blad TypeSafe lub OTHER zostawia stary matcher.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from app.modules.matcher.result import MatchResult, QUALITY_OK
from app.modules.matcher.shared import apply_warehouse_variant, resolve_by_kod
from app.modules.matcher.special_rules import SpecialRule, evaluate_special_rules, find_matching_special_rule
from app.modules.products import Catalog

from .jev_client import jev_enabled, jev_mode
from .jev_shadow import evaluate_shadow

logger = logging.getLogger(__name__)
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
        if not locked and result.jev_kod:
            candidate = catalog.find_by_kod(result.jev_kod)
            if candidate is not None:
                candidate = apply_warehouse_variant(catalog, candidate, magazyn)
                item["match_kod"] = candidate.kod
                item["match_nazwa"] = candidate.nazwa
                item["match_jm"] = candidate.jm
                item["matched_product_id"] = resolve_product_id(candidate.kod)
                item["match_quality"] = QUALITY_OK
                item["match_score"] = float(result.confidence)
                applied = candidate.kod != current_match.kod
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
            },
            "candidate_codes": [c.kod for c in result.candidates],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "duration_ms": result.duration_ms,
            "applied": applied,
            "locked_by_special_rule": locked,
        })

    return out
