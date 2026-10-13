"""Prewarmed streaming bridge: read Claude OCR pages on stdin NDJSON, run JEV in parallel.

Manual benchmark, no document updates, no SQL writes, no generated TXT.
Run in the existing Multiplekser worker container with PYTHONPATH=/app.
Protocol input: {"page":1,"rows":[{"nazwa":"...","ilosc_wydana":1,"ilosc_zuzyta":1}]}
Protocol output: {"kind":"ready"...}, {"kind":"result","page":1,...}
"""
from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import threading
import time
from uuid import UUID
from app.modules.documents.tasks import dispatch_groq_shadow_task
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.products import Catalog
from app.modules.matcher import match_against_catalog_hydraulika, match_against_catalog
from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA
from app.modules.matcher.special_rules import rules_from_db
from app.modules.decision.active import apply_jev_active
from app.modules.ocr.parsing import parse_float_loose

LOCK=threading.Lock()
def emit(event):
    with LOCK:
        sys.stdout.write(json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n")
        sys.stdout.flush()

def num(v):
    return parse_float_loose(str(v)) if v is not None and v!="" else None

def page_decisions(payload, catalog, rules, dzial, magazyn):
    t0=time.perf_counter()
    original_rows=payload["rows"]
    page=payload["page"]
    items=[]
    for entry in original_rows:
        name=str(entry.get("nazwa") or "").strip()
        if not name:continue
        match=(match_against_catalog_hydraulika(
            name,catalog,magazyn=magazyn,special_rules=rules
        ) if dzial=="hydraulika" else match_against_catalog(
            name,catalog,magazyn=magazyn,special_rules=rules
        ))
        items.append(dict(
            rozpoznana_nazwa=name,
            ilosc_wydana=num(entry.get("ilosc_wydana")),
            ilosc_zuzyta=num(entry.get("ilosc_zuzyta")),
            match_kod=match.kod,match_nazwa=match.nazwa,match_jm=match.jm_override,
            match_quality=match.quality,match_score=match.ratio,
            matched_product_id=None,needs_review=False,form_note="",
        ))
    before=[(x["ilosc_wydana"],x["ilosc_zuzyta"]) for x in items]
    if not items:
        emit({"kind":"result","page":page,"error":"no rows"})
        return
    decisions=asyncio.run(apply_jev_active(
        items=items,catalog=catalog,special_rules=rules,
        magazyn=magazyn,dzial=dzial,resolve_product_id=lambda _code:None
    ))
    assert before==[(x["ilosc_wydana"],x["ilosc_zuzyta"]) for x in items]
    flags={row["sequence"]:row for row in decisions}
    out=[]
    for i,item in enumerate(items):
        decision=flags.get(i)
        out.append({
            "name":item["rozpoznana_nazwa"],
            "w":item["ilosc_wydana"],"z":item["ilosc_zuzyta"],
            "code":item["match_kod"],
            "jev_code":decision["jev_kod"] if decision else None,
            "jev_applied":bool(decision and decision["applied"]),
            "review":bool(item["needs_review"]),
        })
    emit({
        "kind":"result","page":page,"rows":out,
        "count":len(items),"jev_responses":len(decisions),
        "jev_seconds":round(time.perf_counter()-t0,2),
        "qty_unchanged":True,
        "jev_changes":sum(x["jev_applied"] for x in out),
        "reviews":sum(x["review"] for x in out),
    })


def main():
    document_id=UUID(sys.argv[1])
    db=SessionLocal()
    try:
        doc=db.get(DocumentModel,document_id)
        assert doc is not None and doc.status=="done" and doc.dzial in {"hydraulika","elektryka"}
        dzial=doc.dzial
        magazyn=doc.magazyn
        catalog=Catalog.from_db(db,dzial=dzial)
        rules=(DEFAULT_SPECIAL_RULES_HYDRAULIKA if dzial=="hydraulika" else rules_from_db(db))
    finally:
        db.rollback()
        db.close()
    with ThreadPoolExecutor(max_workers=3) as pool:
        emit({"kind":"ready","dzial":dzial,"magazyn":magazyn})
        futures=[]
        for line in sys.stdin:
            if not line.strip():continue
            data=json.loads(line)
            if data.get("kind")=="close":break
            assert isinstance(data.get("rows"),list)
            assert data.get("page") in (1,2,3)
            futures.append(pool.submit(page_decisions,data,catalog,rules,dzial,magazyn))
        for f in futures:f.result()
    emit({"kind":"complete","pages":len(futures)})

if __name__=="__main__":
    main()
