#!/usr/bin/env python3
"""Claude Pro document OCR host daemon — official Claude Code, filesystem IPC.

Runs on owner's VPS, authenticated by the owner's existing Claude Code OAuth.
Never passes OAuth token into Docker, never executes tools supplied by AI.
One job at a time (three document pages run in parallel) to limit Pro usage.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

ROOT=Path("/var/lib/multiplekser-claude-bridge/jobs")
CLAUDE="/root/.nvm/versions/node/v22.23.2/bin/claude"
STOP=False
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("multiplekser-claude-bridge")

BASE_PROMPT=(
    "OCR tabeli z wydawki. Tylko wiersze z wpisem ręcznym w kolumnie wydana lub zużyta. "
    "Dwie kolumny niezależne, nie zgaduj, ptaszek nie jest cyfrą. "
    "Przepisz pełne nazwy materiałów bez kodów i decyzji. "
    "Odpowiedz WYŁĄCZNIE zwięzłym JSON bez Markdown: "
    '{"p":[["Nazwa materiału",2,1],["Inny materiał",1,null]]}.'
    " W każdej trójce: nazwa, ilość wydana, ilość zużyta."
)


def read_page(job:Path,page:int,dzial:str)->dict:
    image=job/f"page{page}.jpg"
    raw=image.read_bytes()
    if raw[:2] != bytes((255, 216)) or len(raw)>8_000_000:
        raise ValueError(f"Strona {page} nie jest prawidłowym JPG")
    prompt=BASE_PROMPT
    if dzial=="elektryka":
        prompt += (
            " To formularz elektryczny. Rozróżniaj 1P/3P, PL/DE, kolor, amperaż, "
            "natynkowe/podtynkowe i numery typów. Nie zmieniaj literalnych nazw."
        )
    payload=[{"type":"text","text":prompt},
             {"type":"image","source":{"type":"base64","media_type":"image/jpeg",
                                      "data":base64.b64encode(raw).decode("ascii")}}]
    message={"type":"user","message":{"role":"user","content":payload},"parent_tool_use_id":None}
    env=os.environ.copy()
    for key in ("ANTHROPIC_API_KEY","ANTHROPIC_AUTH_TOKEN","ANTHROPIC_BASE_URL","ANTHROPIC_MODEL"):
        env.pop(key,None)
    command=[
        CLAUDE,"--print","--input-format","stream-json","--output-format","stream-json",
        "--verbose","--restricted","--strict-mcp-config","--disable-slash-commands",
        "--tools","","--model","sonnet","--effort","low","--max-turns","1",
        "--no-session-persistence",
    ]
    started=time.monotonic()
    run=subprocess.run(command,input=json.dumps(message,ensure_ascii=False)+"\n",
        cwd=job,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        timeout=125,check=False)
    reply=None
    for line in run.stdout.splitlines():
        try: event=json.loads(line)
        except ValueError:continue
        if event.get("type")=="result":
            if event.get("is_error"):raise ValueError(str(event.get("result") or "Błąd Claude")[:240])
            reply=event.get("result")
    if run.returncode or not isinstance(reply,str):
        raise RuntimeError(f"Claude nie zwrócił wyniku dla strony {page}; exit={run.returncode}")
    reply=reply.strip()
    if reply.startswith("```"):
        reply=re.sub(r"^\x60{3}(?:json)?\s*","",reply)
        reply=re.sub(r"\s*\x60{3}$","",reply)
    data=json.loads(reply)
    triples=data.get("p")
    if not isinstance(triples,list) or len(triples)>140:
        raise ValueError("Claude nie zwrócił prawidłowej tabeli OCR")
    rows=[]
    for row in triples:
        if not isinstance(row,list) or len(row)!=3 or not isinstance(row[0],str):
            raise ValueError("Nieprawidłowy format pojedynczego wiersza Claude")
        rows.append({"nazwa":row[0],"ilosc_wydana":row[1],"ilosc_zuzyta":row[2]})
    return {"index":page,"rows":rows,"seconds":round(time.monotonic()-started,2)}


def process_job(job:Path,request:dict):
    start=time.monotonic()
    try:
        if str(uuid.UUID(request["job_id"]))!=job.name:
            raise ValueError("Niepoprawny identyfikator zadania")
        count=request["pages"]
        dzial=request["dzial"]
        if not isinstance(count,int) or not 1<=count<=6 or dzial not in {"elektryka","hydraulika"}:
            raise ValueError("Nieprawidłowe parametry żądania Claude")
        with ThreadPoolExecutor(max_workers=min(count,3)) as pool:
            futures={pool.submit(read_page,job,page,dzial):page for page in range(1,count+1)}
            pages=[f.result() for f in as_completed(futures)]
        pages.sort(key=lambda item:item["index"])
        result={"pages":pages,"total_seconds":round(time.monotonic()-start,2)}
        log.info("Claude job completed id=%s pages=%s time=%.2fs",job.name,count,result["total_seconds"])
    except (Exception,KeyboardInterrupt) as exc:
        result={"error":f"{type(exc).__name__}: {str(exc)[:190]}"}
        log.warning("Claude job failed id=%s type=%s",job.name,type(exc).__name__)
    try:
        temp=job/"result.tmp"
        temp.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
        # Filesystem IPC: worker UID owns the job directory. The private result
        # must be readable by that same user, not only by root host daemon.
        owner=job.stat()
        os.chown(temp, owner.st_uid, owner.st_gid)
        temp.chmod(0o600)
        temp.replace(job/"result.json")
    except OSError:
        log.warning("Job disappeared while returning result id=%s",job.name)


def main():
    global STOP
    def stop(_signal,_frame):
        global STOP
        STOP=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    ROOT.mkdir(parents=True,exist_ok=True)
    os.umask(0o077)
    log.info("Claude bridge started; scanning private job directory")
    while not STOP:
        for job in sorted(ROOT.iterdir()):
            if STOP:break
            if not job.is_dir() or not re.fullmatch(r"[0-9a-f-]{36}",job.name):
                continue
            queued=job/"request.json"
            running=job/"processing.json"
            if not queued.is_file():continue
            try:
                queued.rename(running)
                request=json.loads(running.read_text(encoding="utf-8"))
                process_job(job,request)
            except (OSError,ValueError,KeyError) as exc:
                log.warning("Cannot claim job %s: %s",job.name,type(exc).__name__)
        time.sleep(0.2)
    log.info("Claude bridge stopped")


if __name__=="__main__":
    main()
