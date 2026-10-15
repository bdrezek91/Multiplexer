"""One-off read-only JEV Image ONLY historical evaluation on stored PDFs.

Example (in isolated Docker):
 python -m scripts.benchmark_jev_vision_only --limit 3 --max-marked 6
Outputs private JSON on a mounted directory. No production mutations.
"""
from __future__ import annotations
import argparse,hashlib,json,os,time
from pathlib import Path
from sqlalchemy import text
import app.main  # Ensure all SQLAlchemy models are registered for read-only catalog queries.
from app.core.db import engine, SessionLocal
from app.modules.jev_vision_only.matcher_shadow import suggest_matches
from app.modules.documents.storage import get_storage
from app.modules.jev_vision_only.engine import analyze_pdf
from app.modules.jev_vision_only.geometry import render_pdf_pages,detect_page,LayoutUncertain

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--limit",type=int,default=2)
    ap.add_argument("--max-marked",type=int,default=6)
    ap.add_argument("--department",choices=("elektryka","hydraulika"),default=None)
    ap.add_argument("--geometry-only",action="store_true")
    ap.add_argument("--sha-file",default=None,help="Frozen evaluation cohort, sha256 prefixes, one per line")
    ap.add_argument("--suggest-matches",action="store_true",help="Existing deterministic matcher, proposals only")
    ap.add_argument("--verify-quantities",action="store_true",help="Second independent enhanced-image quantity check")
    ap.add_argument("--out",default="/shadow/jev_only_e0.json")
    args=ap.parse_args()
    assert 1<=args.limit<=12 and 1<=args.max_marked<=20
    out=Path(args.out);out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    with engine.connect() as conn:
        docs=conn.execute(text("""SELECT id,file_key,dzial,magazyn FROM document
            WHERE status='done' AND mime='application/pdf'
              AND (:department IS NULL OR dzial = :department)
            ORDER BY created_at DESC LIMIT 200"""), {"department":args.department}).all()
    store=get_storage();done=[];seen=set()
    cohort=[x.strip() for x in Path(args.sha_file).read_text().splitlines() if x.strip()] if args.sha_file else []
    if cohort and (len(cohort)>40 or any(len(x)!=12 or not all(ch in "0123456789abcdef" for ch in x) for x in cohort)):
        raise ValueError("invalid frozen cohort sha256 prefixes")
    scanned=[]
    for uid,key,department,magazyn in docs:
        data=store.download(key);sha=hashlib.sha256(data).hexdigest()
        if sha in seen:continue
        seen.add(sha)
        if cohort and sha[:12] not in cohort:continue
        start=time.monotonic()
        if args.geometry_only:
            measurements=[]
            for i,page in enumerate(render_pdf_pages(data),1):
                try:
                    grid,rows=detect_page(page,i)
                    measurements.append({"page":i,"grid_rows":len(rows),
                              "marked_rows":sum(x.issued_ink>=8 or x.used_ink>=8 for x in rows),
                              "columns":grid.columns})
                except LayoutUncertain as exc:
                    measurements.append({"page":i,"uncertain":str(exc)})
            report={"status":"geometry_only","diagnostics":measurements}
        else:
            report=analyze_pdf(data,department,max_marked=args.max_marked,verify_quantities=args.verify_quantities)
            if args.suggest_matches and report.get("status")=="shadow_experimental":
                with SessionLocal() as session:
                    report=suggest_matches(report,session,magazyn)
        elapsed=round(time.monotonic()-start,3)
        record={"document_sha256_prefix":sha[:12],"department":department,
                "seconds":elapsed,"result":report}
        done.append(record)
        print("DOC",len(done),department,"RESULT",report["status"],
              "SECONDS",elapsed,"GRID",report.get("grid_rows_found",0),
              "CANDIDATES",report.get("candidates_total",0),
              "ASKED",len(report.get("rows",[])),flush=True)
        if len(done)>=args.limit and not cohort:break
        if cohort and len(done)>=len(cohort):break
    if cohort and set(cohort)!={x["document_sha256_prefix"] for x in done}:
        raise RuntimeError("frozen cohort incomplete: not all documents found")
    if cohort:done.sort(key=lambda x:cohort.index(x["document_sha256_prefix"]))
    out.write_text(json.dumps(done,ensure_ascii=False,indent=2))
    os.chmod(out,0o600)
    print("READ_ONLY_REPORT",out,"COUNT",len(done),flush=True)

if __name__=="__main__":main()
