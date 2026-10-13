#!/usr/bin/env python3
"""Score Claude rapid OCR reports against partly visually-corrected 43-row reference.

Does not write DB or TXT. Output reports are private on VPS, not committed.
"""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path("/var/tmp/multiplekser_claude_shadow")
SPEED=ROOT/"speed"
PATCH=json.loads((ROOT/"bench/reviewed_reference_patch.json").read_text())
CASES={
    "parallel3":["sonnet_low_concurrent_1","sonnet_low_concurrent_2","sonnet_low_concurrent_3"],
    "all3":["sonnet_low_inline_all3"],
    "compact_parallel":["sonnet_compact_parallel_p1","sonnet_compact_parallel_p2","sonnet_compact_parallel_p3"],
    "compact_stream":["sonnet_compact_stream_p1","sonnet_compact_stream_p2","sonnet_compact_stream_p3"],
    "fast_stream_repeat":["fast_sonnet_low_p1","fast_sonnet_low_p2","fast_sonnet_low_p3"],
}
for extra in sys.argv[1:]:
    p=SPEED/f"{extra}.json"
    if p.exists():CASES[extra]=[extra]
data={}
for key,names in CASES.items():
    paths=[SPEED/f"{name}.json" for name in names]
    if not all(p.exists() for p in paths):continue
    reports=[json.loads(p.read_text()) for p in paths]
    rows=[r for rep in reports for r in rep["rows"]]
    data[key]={"rows":rows,"seconds":max(r["seconds"] for r in reports)
                if len(reports)>1 else reports[0]["seconds"]}
if not data:raise SystemExit("No reports")
code=r'''
import json,sys
from uuid import UUID
from types import SimpleNamespace
from app.modules.documents.tasks import dispatch_groq_shadow_task
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.documents.background_verification import _background_review_item
from app.modules.documents.groq_shadow import _compare_shadow
from app.modules.products.catalog import plain_norm
request=json.load(sys.stdin)
s=SessionLocal()
try:
    doc=s.get(DocumentModel,UUID(request['document_id']))
    assert doc is not None and doc.status=="done" and doc.dzial=="hydraulika"
    main=[dict(x) for item in doc.items if (x:=_background_review_item(item)) is not None]
    for patch in request['patches']:
        hit=[r for r in main if plain_norm(str(r['rozpoznana_nazwa']))==plain_norm(patch['from'])]
        assert len(hit)==1,patch
        row=hit[0]
        if 'to' in patch:row['rozpoznana_nazwa']=patch['to']
        if 'qty' in patch:row['ilosc_wydana'],row['ilosc_zuzyta']=patch['qty']
    out={}
    for key,case in request['cases'].items():
        inp=[SimpleNamespace(rozpoznana_nazwa=x.get('nazwa',''),ilosc_wydana=x.get('ilosc_wydana'),
                             ilosc_zuzyta=x.get('ilosc_zuzyta')) for x in case['rows']]
        metrics=_compare_shadow(main,inp)
        out[key]={'seconds':case['seconds'],'recognized':len(inp),**metrics}
    print(json.dumps(out,ensure_ascii=False))
finally:s.close()
'''
r=subprocess.run(["docker","exec","-i","-w","/app","multiplekser-backend-1",
    "python","-c",code],input=json.dumps({"document_id":PATCH["document_id"],
    "patches":PATCH["patches"],"cases":data}),capture_output=True,text=True,timeout=55)
if r.returncode:raise RuntimeError(r.stderr[-1200:])
results=json.loads(r.stdout)
for label,x in results.items():
    print("FAST_SCORE",label,"seconds",x["seconds"],"rows",x["recognized"],
        "matched",x["matched"],"qty_exact",x["exact_qty"],"mismatch",x["mismatch_count"],
        "shadow_only",x["shadow_only"],"main_only",x["main_only"],flush=True)
    print("DIFFS",x["mismatches"],flush=True)
target=SPEED/"accuracy_results.json"
target.write_text(json.dumps({"basis":"43 prod + 4 visual patches (not independent full GOLD)",
    "results":results},ensure_ascii=False,indent=2))
target.chmod(0o600)
