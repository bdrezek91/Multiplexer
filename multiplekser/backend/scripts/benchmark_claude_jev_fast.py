#!/usr/bin/env python3
"""Measure genuine wall time of Claude image OCR per page + prewarmed JEV decisions.

Start timer when warmed JEV is ready; run Claude Sonnet Low 3 pages concurrently.
Feed each completed page to Jev ASAP while other Claude calls still run.
NO database modifications, NO production OCR/TXT changes, manual benchmark only.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json
import subprocess
import time
import os

SCRIPT=Path("/root/Multiplexer/multiplekser/backend/scripts/benchmark_claude_inline_vision.py")
ROOT=Path("/var/tmp/multiplekser_claude_shadow/speed")
ID="7b2ff45a-2dac-4f54-864d-41938fed7597"

def one_page(p, profile):
    model,effort=(("opus","high") if p==1 else ("opus","medium") if p==2 else ("sonnet","low")) if profile=="mixed" else ("sonnet","low")
    label=f"{profile}_{model}_{effort}_p{p}"
    cmd=["python3",str(SCRIPT),"--pages",str(p),
         "--model",model,"--effort",effort,"--compact","--force","--label",label]
    start=time.perf_counter()
    run=subprocess.run(cmd,text=True,capture_output=True,timeout=145)
    if run.returncode:
        raise RuntimeError(f"Claude page {p} failed: {run.stdout[-160:]} {run.stderr[-160:]}")
    output=json.loads((ROOT/f"{label}.json").read_text())
    return {"page":p,"rows":output["rows"],"claude_seconds":output["seconds"],
            "completed_at":time.perf_counter()}

def main(profile="fast"):
    cmd=["docker","exec","-i","-w","/app","-e","PYTHONPATH=/app",
         "multiplekser-worker-1","python","/tmp/jev_stream_shadow.py",ID]
    sidecar=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,text=True,bufsize=1)
    try:
        first=sidecar.stdout.readline()
        ready=json.loads(first)
        if ready.get("kind")!="ready":
            raise RuntimeError("JEV not ready: "+first[:150])
        start=time.perf_counter()
        summary={"jev_ready_preheated":True,"pages":[]}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures={pool.submit(one_page,p,profile):p for p in (1,2,3)}
            for future in as_completed(futures):
                page=future.result()
                summary["pages"].append({"page":page["page"],"ocr_seconds":page["claude_seconds"],
                       "ocr_at":round(page["completed_at"]-start,3),"rows":len(page["rows"])})
                sidecar.stdin.write(json.dumps({"page":page["page"],"rows":page["rows"]},
                                               ensure_ascii=False)+"\n")
                sidecar.stdin.flush()
        sidecar.stdin.write('{"kind":"close"}\n')
        sidecar.stdin.flush()
        sidecar.stdin.close()
        sidecar.stdin=None
        output,stderr=sidecar.communicate(timeout=45)
        wall=round(time.perf_counter()-start,3)
        results=[]
        for line in output.splitlines():
            try: event=json.loads(line)
            except ValueError: continue
            if event.get("kind")=="result":
                results.append(event)
        summary["wall_seconds"]=wall
        summary["jev_pages"]=len(results)
        summary["jev_responses"]=sum(x.get("jev_responses",0) for x in results)
        summary["rows_final"]=sum(x.get("count",0) for x in results)
        summary["jev_changes"]=sum(x.get("jev_changes",0) for x in results)
        summary["reviews"]=sum(x.get("reviews",0) for x in results)
        summary["jev_max_seconds"]=max((x.get("jev_seconds",0) for x in results),default=None)
        summary["qty_unchanged"]=all(x.get("qty_unchanged") for x in results)
        summary["complete"]=sidecar.returncode==0 and len(results)==3 and summary["jev_responses"]==43
        print("FULL_BENCHMARK",json.dumps({k:v for k,v in summary.items() if k!="pages"},ensure_ascii=False))
        print("PAGES",summary["pages"])
        if not summary["complete"]: print("SIDECAR_ERROR",stderr[-350:])
        outputfile=ROOT/f"{profile}_stream_end2end.json"
        os.umask(0o077)
        outputfile.write_text(json.dumps({"summary":summary,"rows":results},ensure_ascii=False,indent=2))
        outputfile.chmod(0o600)
        if not summary["complete"]: raise SystemExit(7)
    finally:
        if sidecar.poll() is None: sidecar.kill();sidecar.wait()

if __name__=="__main__":
    import sys
    arg=sys.argv[1] if len(sys.argv)>1 else "fast"
    if arg not in ("fast","mixed"):raise SystemExit("BAD_PROFILE")
    main(arg)
