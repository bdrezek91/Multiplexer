"""PoC: jeden request Jev dla calej historycznej wydawki.

Skrypt jest READ-ONLY wzgledem bazy. Nie zmienia Document/DocumentItem ani wynikow produkcyjnych.
Porownuje decyzje Jev z zapisanym koncowym match_kod dla kazdego wiersza.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import httpx
from sqlalchemy.orm import selectinload

from app.core.db import SessionLocal
from app.modules.decision.jev_client import TYPESAFE_SYSTEMONE_URL, jev_model
from app.modules.decision.jev_shadow import (
    _query_features,
    _soft_matcher_rules,
    build_shortlist,
)
from app.modules.users.models import UserModel  # noqa: F401 - rejestracja relacji ORM
from app.modules.products.models import ProductModel  # noqa: F401 - rejestracja relacji ORM
from app.modules.documents.models import DocumentModel
from app.modules.matcher.result import MatchResult
from app.modules.products import Catalog

BATCH_TIMEOUT_SECONDS = 20.0


def _candidate_dict(candidate):
    return {
        "id": candidate.key,
        "kod": candidate.kod,
        "nazwa": candidate.nazwa,
        "jm": candidate.jm,
        "grupa": candidate.grupa,
        "atrybuty": candidate.atrybuty,
        "aliasy_z_wydawek": candidate.aliasy,
        "diagnostics": candidate.diagnostics,
    }


async def evaluate_document(document, catalog, chunk_size: int = 6):
    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Brak TYPESAFE_API_KEY")

    all_context_rows = []
    decisions = []

    for index, item in enumerate(document.items):
        name = (item.rozpoznana_nazwa or "").strip()
        if not name:
            continue

        row_id = f"R{index}"
        all_context_rows.append({
            "row_id": row_id,
            "ocr_text": name,
            "wydana": item.ilosc_wydana,
            "zuzyta": item.ilosc_zuzyta,
        })

        current_match = MatchResult(
            kod=item.match_kod,
            nazwa=item.match_nazwa,
            quality=item.match_quality,
            ratio=item.match_score or 0.0,
            jm_override=item.match_jm,
        )
        candidates = build_shortlist(
            query_name=name,
            catalog=catalog,
            current_match=current_match,
            dzial=document.dzial or "elektryka",
            magazyn=document.magazyn,
            limit=5,
            include_current_match=False,
        )
        if not candidates:
            continue

        features = _query_features(name, document.dzial or "elektryka")
        decisions.append({
            "row_id": row_id,
            "sequence": item.sequence,
            "ocr_text": name,
            "matcher_kod": item.match_kod,
            "query_features": features,
            "soft_rules": _soft_matcher_rules(features),
            "candidates": candidates,
        })

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    results = []
    total_duration_ms = 0
    total_input_tokens = 0
    total_output_tokens = 0
    model_name = jev_model()

    for chunk_start in range(0, len(decisions), chunk_size):
        chunk = decisions[chunk_start:chunk_start + chunk_size]
        questions = {}
        key_to_code = {}
        decision_rows = []

        for offset, row in enumerate(chunk):
            question_id = f"produkt_{row['sequence']}"
            candidates = row["candidates"]
            decision_rows.append({
                "row_id": row["row_id"],
                "ocr_text": row["ocr_text"],
                "query_features": row["query_features"],
                "soft_rules": row["soft_rules"],
                "candidates": [
                    {
                        "id": c.key,
                        "kod": c.kod,
                        "nazwa": c.nazwa,
                        "aliasy": c.aliasy[:3],
                        "diagnostics": c.diagnostics,
                    }
                    for c in candidates
                ],
            })
            criteria = {c.key: f"{c.kod} | {c.nazwa}" for c in candidates}
            criteria["OTHER"] = "Zaden kandydat nie pasuje."
            questions[question_id] = {
                "type": "choice",
                "instructions": (
                    f"Wybierz produkt tylko dla {row['row_id']}. "
                    "W state masz cala wydawke jako context_rows oraz szczegoly tej pozycji "
                    "w decision_rows. Uzyj cech, aliasow i diagnostyki. "
                    "Jesli nic nie pasuje, wybierz OTHER."
                ),
                "criteria": criteria,
            }
            key_to_code[question_id] = {c.key: c.kod for c in candidates}
            key_to_code[question_id]["OTHER"] = None

        payload = {
            "model": jev_model(),
            "state": {
                "document": {
                    "numer_projektu": document.numer_projektu,
                    "magazyn": document.magazyn,
                },
                "context_rows": all_context_rows,
                "decision_rows": decision_rows,
                "rules": [
                    "Kazdy wiersz jest osobna pozycja tej samej wydawki.",
                    "Kontekst innych wierszy pomaga rozumiec skroty, ale nie wolno przenosic produktu miedzy wierszami.",
                    "Brak jawnego 3P oznacza 1P.",
                ],
            },
            "questions": questions,
        }

        started = time.perf_counter()
        async with asyncio.timeout(BATCH_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=BATCH_TIMEOUT_SECONDS) as client:
                response = await client.post(TYPESAFE_SYSTEMONE_URL, headers=headers, json=payload)
        total_duration_ms += round((time.perf_counter() - started) * 1000)

        if response.status_code != 200:
            raise RuntimeError(
                f"TypeSafe HTTP {response.status_code} chunk={chunk_start // chunk_size + 1}: "
                f"{response.text[:500]}"
            )

        data = response.json()
        model_name = data.get("model") or model_name
        usage = data.get("usage") or {}
        total_input_tokens += int(usage.get("input_tokens") or 0)
        total_output_tokens += int(usage.get("output_tokens") or 0)
        answers = data.get("answers") or {}

        for row in chunk:
            question_id = f"produkt_{row['sequence']}"
            answer = answers.get(question_id) or {}
            choice = str(answer.get("choice") or "").strip()
            jev_kod = key_to_code.get(question_id, {}).get(choice)
            matcher_kod = row["matcher_kod"]
            results.append({
                "sequence": row["sequence"],
                "ocr_text": row["ocr_text"],
                "matcher_kod": matcher_kod,
                "jev_kod": jev_kod,
                "choice": choice,
                "confidence": answer.get("confidence"),
                "agrees": bool(matcher_kod and jev_kod and matcher_kod == jev_kod),
                "other": choice == "OTHER",
                "matcher_in_shortlist": matcher_kod in {c.kod for c in row["candidates"]},
            })

    return {
        "document_id": str(document.id),
        "numer_projektu": document.numer_projektu,
        "rows": results,
        "duration_ms": total_duration_ms,
        "model": model_name,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "requests": (len(decisions) + chunk_size - 1) // chunk_size,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        query = (
            session.query(DocumentModel)
            .options(selectinload(DocumentModel.items))
            .filter(DocumentModel.status == "done", DocumentModel.dzial == "elektryka")
            .order_by(DocumentModel.created_at.desc())
        )
        if args.project:
            query = query.filter(DocumentModel.numer_projektu == args.project)
        docs = query.limit(args.limit).all()
        catalog = Catalog.from_db(session, dzial="elektryka")

        total_rows = total_agree = total_other = total_shortlist = 0
        summaries = []
        for document in docs:
            try:
                result = await evaluate_document(document, catalog)
            except Exception as exc:
                print("ERROR", json.dumps({
                    "project": document.numer_projektu,
                    "error": str(exc),
                }, ensure_ascii=False))
                continue

            rows = result["rows"]
            agree = sum(1 for r in rows if r["agrees"])
            other = sum(1 for r in rows if r["other"])
            shortlist = sum(1 for r in rows if r["matcher_in_shortlist"])
            total_rows += len(rows)
            total_agree += agree
            total_other += other
            total_shortlist += shortlist
            summary = {
                "project": result["numer_projektu"],
                "rows": len(rows),
                "requests": result["requests"],
                "agree": agree,
                "agree_pct": round(100 * agree / len(rows), 1) if rows else 0,
                "other": other,
                "matcher_in_shortlist": shortlist,
                "duration_ms": result["duration_ms"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "model": result["model"],
            }
            summaries.append(summary)
            print("DOCUMENT", json.dumps(summary, ensure_ascii=False))
            for row in rows:
                if not row["agrees"]:
                    print("DIFF", json.dumps({
                        "project": result["numer_projektu"],
                        **row,
                    }, ensure_ascii=False, default=str))

        print("TOTAL", json.dumps({
            "documents": len(summaries),
            "rows": total_rows,
            "agree": total_agree,
            "agree_pct": round(100 * total_agree / total_rows, 1) if total_rows else 0,
            "other": total_other,
            "matcher_in_shortlist": total_shortlist,
            "matcher_in_shortlist_pct": round(100 * total_shortlist / total_rows, 1) if total_rows else 0,
            "duration_ms": sum(s["duration_ms"] for s in summaries),
            "input_tokens": sum(s["input_tokens"] for s in summaries),
            "output_tokens": sum(s["output_tokens"] for s in summaries),
        }, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
