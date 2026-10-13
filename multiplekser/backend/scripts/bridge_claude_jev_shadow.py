"""Manual read-only Claude OCR -> matcher -> TypeSafe Jev ACTIVE benchmark.

Invoke inside worker container with 3 Claude OCR page results combined on stdin:
    python3 /app/scripts/bridge_claude_jev_shadow.py --document-id UUID --limit 12

This NEVER writes DB, never calls generated TXT/Optima, and keeps original OCR
quantities untouched. It runs the same apply_jev_active path used in production
with Hydraulika special rules and proper catalog/magazine.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from app.modules.documents.tasks import dispatch_groq_shadow_task  # ORM model registration
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.decision.active import apply_jev_active
from app.modules.matcher import match_against_catalog_hydraulika
from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA
from app.modules.products import Catalog
from app.modules.ocr.parsing import parse_float_loose


def main(document_id: str, limit: int) -> int:
    if not 1 <= limit <= 43:
        raise ValueError("limit musi byc 1-43")
    entries = json.load(sys.stdin)
    if not isinstance(entries, list) or not entries:
        raise ValueError("Wymagana lista surowych wierszy OCR Claude")
    db = SessionLocal()
    try:
        doc = db.get(DocumentModel, UUID(document_id))
        if doc is None or doc.dzial != "hydraulika" or doc.status != "done":
            raise ValueError("Dokument benchmarkowy musi byc zakonczona hydraulika")
        catalog = Catalog.from_db(db, dzial="hydraulika")
        items = []
        base = []
        for entry in entries:
            name = str(entry.get("nazwa") or "").strip()
            if not name:
                continue
            match = match_against_catalog_hydraulika(
                name, catalog, magazyn=doc.magazyn,
                special_rules=DEFAULT_SPECIAL_RULES_HYDRAULIKA,
            )
            def qty(key):
                val=entry.get(key)
                if val is None or val=="":
                    return None
                return parse_float_loose(str(val))
            row = {
                "rozpoznana_nazwa": name,
                "ilosc_wydana": qty("ilosc_wydana"),
                "ilosc_zuzyta": qty("ilosc_zuzyta"),
                "match_kod": match.kod,
                "match_nazwa": match.nazwa,
                "match_jm": match.jm_override,
                "match_quality": match.quality,
                "match_score": match.ratio,
                "matched_product_id": None,
                "needs_review": False,
                "form_note": "",
            }
            items.append(row)
        if not items:
            raise ValueError("Brak pozycji OCR Claude")
        # Prefer weak matches for real change/OTHER validation; maintain traceable index.
        indexed = sorted(
            enumerate(items),
            key=lambda x: (
                0 if x[1]["match_quality"]=="bad" else 1,
                x[1]["match_score"],
                x[0],
            ),
        )[:limit]
        selection = [dict(row) for _, row in indexed]
        qty_before = [(x["ilosc_wydana"], x["ilosc_zuzyta"]) for x in selection]
        results = asyncio.run(apply_jev_active(
            items=selection, catalog=catalog,
            special_rules=DEFAULT_SPECIAL_RULES_HYDRAULIKA,
            magazyn=doc.magazyn, dzial="hydraulika",
            resolve_product_id=lambda code: None,  # shadow run
        ))
        assert qty_before == [(x["ilosc_wydana"], x["ilosc_zuzyta"]) for x in selection], (
            "JEV zmienil ilosci OCR - niedopuszczalne"
        )
        decision_by_seq = {x["sequence"]: x for x in results}
        rows = []
        for seq, ((original_idx, original), new) in enumerate(zip(indexed, selection)):
            detail = decision_by_seq.get(seq)
            rows.append({
                "index": original_idx,
                "claude_name": original["rozpoznana_nazwa"],
                "claude_qty_wydana": original["ilosc_wydana"],
                "claude_qty_zuzyta": original["ilosc_zuzyta"],
                "matcher_quality": original["match_quality"],
                "matcher_code": original["match_kod"],
                "jev_code": detail["jev_kod"] if detail else None,
                "jev_confidence": detail["confidence"] if detail else None,
                "final_code": new["match_kod"],
                "jev_applied": bool(detail and detail["applied"]),
                "review": bool(new["needs_review"]),
                "reason": (
                    "no_jev_response" if not detail else
                    "protected_feature_conflict"
                    if detail["query_features"].get("active_rejected_by_hydraulika_attrs") else
                    "locked_rule" if detail["locked_by_special_rule"] else
                    "normal"
                ),
            })
        summary = {
            "status": "shadow_only",
            "document_id": str(doc.id),
            "numer_projektu": doc.numer_projektu,
            "dzial": doc.dzial,
            "magazyn": doc.magazyn,
            "claude_total_rows": len(items),
            "jev_evaluated": len(selection),
            "jev_responses": len(results),
            "jev_applied": sum(x["jev_applied"] for x in rows),
            "jev_review": sum(x["review"] for x in rows),
            "qty_unchanged": True,
            "rows": rows,
        }
        print(json.dumps(summary, ensure_ascii=False))
    finally:
        db.rollback()  # Never persist even accidental writes.
        db.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args=parser.parse_args()
    raise SystemExit(main(args.document_id, args.limit))
