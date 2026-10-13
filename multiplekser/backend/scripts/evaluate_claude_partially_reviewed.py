#!/usr/bin/env python3
"""Partly human-reviewed benchmark: compare OCR against copied production rows
with four visual corrections. Does not change any DB records or user TXT.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess

ROOT = Path("/var/tmp/multiplekser_claude_shadow")
BENCH = ROOT / "bench"

def read_rows(filename: str):
    r = json.loads((ROOT / filename).read_text(encoding="utf-8"))
    return r["ocr"]["pozycje"]

def read_bench(model: str, effort: str, page: int):
    r = json.loads((BENCH / f"{model}_{effort}_page{page}.json").read_text(encoding="utf-8"))
    return r["ocr"]["pozycje"], r["seconds"]

cases = [
    {
        "name":"Sonnet Low (poprzedni pelny)",
        "time_s":69.3,
        "rows":read_rows("report.json")+read_rows("report_page2.json")+read_rows("report_page3.json")
    },
]
o1,t1=read_bench("opus","medium",1)
o2,t2=read_bench("opus","medium",2)
o3,t3=read_bench("opus","medium",3)
h1,th=read_bench("opus","high",1)
cases.extend([
    {"name":"Opus Medium (3 strony)","time_s":round(t1+t2+t3,1),"rows":o1+o2+o3},
    {"name":"Opus High 1 + Medium 2,3","time_s":round(th+t2+t3,1),"rows":h1+o2+o3},
])
manifest=json.loads((BENCH / "reviewed_reference_patch.json").read_text())
patches=manifest["patches"]
code = r"""
import json,sys
from types import SimpleNamespace
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from uuid import UUID
from app.modules.documents.background_verification import _background_review_item
from app.modules.documents.groq_shadow import _compare_shadow
from app.modules.products.catalog import plain_norm

request=json.load(sys.stdin)
s=SessionLocal()
try:
    d=s.get(DocumentModel,UUID(request['document_id']))
    assert d is not None and d.status=='done' and d.dzial=='hydraulika'
    main=[dict(x) for item in d.items if (x:=_background_review_item(item)) is not None]
    assert len(main)==43
    for patch in request['patches']:
        hit=[r for r in main if plain_norm(str(r['rozpoznana_nazwa']))==plain_norm(patch['from'])]
        if len(hit)!=1:raise ValueError('Ref patch did not match exactly one row: '+patch['from'])
        row=hit[0]
        if 'to' in patch:row['rozpoznana_nazwa']=patch['to']
        if 'qty' in patch:
            row['ilosc_wydana'],row['ilosc_zuzyta']=patch['qty']
    summary=[]
    for case in request['cases']:
        rows=case['rows']
        v=[SimpleNamespace(rozpoznana_nazwa=x.get('nazwa',''), ilosc_wydana=x.get('ilosc_wydana'),
                ilosc_zuzyta=x.get('ilosc_zuzyta')) for x in rows]
        metrics=_compare_shadow(main,v)
        summary.append({
            "case":case['name'], "time_s":case['time_s'], "rows":len(rows),
            **metrics
        })
    print(json.dumps(summary,ensure_ascii=False))
finally:s.close()
"""
p=subprocess.run(["docker","exec","-i","-w","/app","multiplekser-backend-1","python","-c",code],
    input=json.dumps({"cases":cases,"patches":patches,"document_id":manifest["document_id"]}),text=True,capture_output=True,timeout=50)
if p.returncode!=0:
    raise RuntimeError(p.stderr[-1200:])
out=json.loads(p.stdout)
for r in out:
    print(f"{r['case']}: rows={r['rows']} labels={r['matched']} "
          f"matching_pairs={r['exact_qty']} mismatched={r['mismatch_count']} "
          f"seconds={r['time_s']}")
    if r['mismatches']:print("MISMATCHES",r['mismatches'])
    if r['main_only']:print("MAIN_ONLY",r['main_only'])
    if r['shadow_only']:print("SHADOW_ONLY",r['shadow_only'])
target=BENCH/"partially_reviewed_comparison.json"
target.write_text(json.dumps({
    "basis":"43 produkcyjne pozycje, 4 wizualne korekty, NIE pelny GOLD",
    "corrections":patches,"comparisons":out
},ensure_ascii=False,indent=2),encoding="utf-8")
target.chmod(0o600)
