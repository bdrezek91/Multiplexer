#!/usr/bin/env python3
"""Compare read-only Claude OCR benchmark to production OCR, not manually validated GOLD."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path("/var/tmp/multiplekser_claude_shadow")
BENCH = ROOT / "bench"

BACKEND_EVALUATOR = r"""
import json,sys
from types import SimpleNamespace
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.documents.background_verification import _background_review_item
from app.modules.documents.groq_shadow import _compare_shadow
from app.modules.products.catalog import plain_norm
session=SessionLocal()
try:
    document=(session.query(DocumentModel)
        .filter(DocumentModel.status=='done',DocumentModel.dzial=='hydraulika')
        .order_by(DocumentModel.created_at.desc()).first())
    if document is None:
        raise ValueError('Brak referencyjnego dokumentu')
    main=[row for item in document.items if (row:=_background_review_item(item)) is not None]
    request=json.load(sys.stdin)
    for case in request.get('cases',[]):
        rows=case['ocr']['pozycje']
        rows=[x for x in rows if isinstance(x,dict) and x.get('nazwa','').strip()]
        items=[SimpleNamespace(rozpoznana_nazwa=x.get('nazwa',''),ilosc_wydana=x.get('ilosc_wydana'),
                               ilosc_zuzyta=x.get('ilosc_zuzyta')) for x in rows]
        metrics=_compare_shadow(main, items)
        case['metrics']={k:v for k,v in metrics.items() if k!='mismatches'}
        case['metrics']['mismatches']=metrics['mismatches']
    print(json.dumps(request,ensure_ascii=False))
finally:
    session.close()
"""


def main() -> None:
    baselines = []
    for page, filename in ((1, "report.json"), (2, "report_page2.json"), (3, "report_page3.json")):
        p = ROOT / filename
        if p.is_file():
            report=json.loads(p.read_text())
            baselines.append({"label":f"sonnet_low_earlier_page{page}",
                              "model":"sonnet","effort":"low",
                              "page":page,"seconds":None,"ocr":report['ocr']})
    cases=baselines
    for p in sorted(BENCH.glob("*.json")) if BENCH.is_dir() else []:
        if p.name == "metrics.json":
            continue
        x=json.loads(p.read_text())
        if not isinstance(x, dict) or "model_alias" not in x:
            continue
        cases.append({"label":p.stem,"model":x["model_alias"],"effort":x["effort"],
                      "page":x["page"],"seconds":x["seconds"],"ocr":x["ocr"]})
    data={"cases":cases}
    result=subprocess.run(
        ["docker","exec","-i","-w","/app","multiplekser-backend-1","python","-c",BACKEND_EVALUATOR],
        input=json.dumps(data),text=True,capture_output=True,timeout=50,check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1600:])
    evaluated=json.loads(result.stdout)
    summary=[]
    for x in evaluated["cases"]:
        m=x["metrics"]
        entry={
            "case":x["label"],"page":x["page"],
            "seconds":x["seconds"],"rows":len(x["ocr"]["pozycje"]),
            "matched_names":m["matched"],
            "both_qty_exact":m["exact_qty"],
            "qty_mismatches":m["mismatch_count"],
            "shadow_only":m["shadow_only_count"],
            "qty_examples":m["mismatches"],
            "unmatched_examples":m["shadow_only"][:3],
        }
        summary.append(entry)
        print(f"{entry['case']:30s} page={entry['page']} rows={entry['rows']:2} "
              f"names={entry['matched_names']:2} both_qty={entry['both_qty_exact']:2} "
              f"mismatches={entry['qty_mismatches']:2} time={entry['seconds']}")
    target=BENCH / "metrics.json"
    BENCH.mkdir(mode=0o700,exist_ok=True)
    target.write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    target.chmod(0o600)


if __name__=="__main__":
    main()
