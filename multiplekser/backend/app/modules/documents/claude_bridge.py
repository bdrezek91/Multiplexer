"""Explicitly opt-in Claude Pro host bridge for Multiplekser test documents.

Keeps OAuth credentials on VPS host, never inside application containers.
Filesystem IPC is private to the worker and the host daemon. A request contains
only JPG pages; output contains only OCR names and both quantity columns.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
import uuid

BRIDGE_ROOT=Path(os.environ.get("CLAUDE_TEST_BRIDGE_DIR", "/claude-bridge"))
MAX_PAGES=6
MAX_IMAGE_BYTES=8_000_000
TIMEOUT_SECONDS=175


class ClaudeBridgeError(RuntimeError):
    pass


def _valid_number(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        raise ClaudeBridgeError("Niepoprawna wartość logiczna ilości z Claude")
    if isinstance(v, (int, float)):
        numeric=float(v)
        if not (numeric > 0 and numeric < 1_000_000):
            raise ClaudeBridgeError("Nieprawidłowa ilość z Claude")
        return str(v)
    raw=str(v).strip().replace(",", ".")
    if not re.fullmatch(r"[0-9]+(?:[.][0-9]+)?",raw):
        raise ClaudeBridgeError("Claude zwrócił nieczytelną ilość: "+raw[:30])
    numeric=float(raw)
    if not (numeric > 0 and numeric < 1_000_000):
        raise ClaudeBridgeError("Claude zwrócił ilość poza zakresem")
    return raw


def validate_ocr(result: dict, page_count: int) -> list[dict]:
    if not isinstance(result,dict) or not isinstance(result.get("pages"),list):
        raise ClaudeBridgeError("Brak danych OCR z Claude")
    pages=result["pages"]
    if len(pages)!=page_count or [p.get("index") for p in pages] != list(range(1,page_count+1)):
        raise ClaudeBridgeError("Claude nie zwrócił wszystkich stron w prawidłowej kolejności")
    all_rows=[]
    for page in pages:
        rows=page.get("rows")
        if not isinstance(rows,list) or len(rows)>140:
            raise ClaudeBridgeError("Nieprawidłowa liczba pozycji na stronie")
        for item in rows:
            if not isinstance(item,dict):
                raise ClaudeBridgeError("Nieprawidłowy format pozycji Claude")
            name=item.get("nazwa")
            if not isinstance(name,str) or not name.strip() or len(name)>250:
                raise ClaudeBridgeError("Nieprawidłowa nazwa pozycji Claude")
            w=_valid_number(item.get("ilosc_wydana"))
            z=_valid_number(item.get("ilosc_zuzyta"))
            all_rows.append({
                "nazwa":name.strip(),"ilosc_wydana":w,
                "ilosc_zuzyta":z,"uwagi":"",
                "page_number":page["index"],
            })
    if not all_rows:
        raise ClaudeBridgeError("Claude nie odczytał żadnej pozycji")
    return all_rows


def run_claude_host_bridge(document_id: str, files: list[tuple[bytes,str]], dzial: str,
                           *, timeout_seconds: float=TIMEOUT_SECONDS) -> tuple[list[dict],float]:
    """Wait for the owner-authenticated host daemon; no Gemini fallback in test mode."""
    if dzial not in {"hydraulika","elektryka"}:
        raise ClaudeBridgeError("Nieznany dział Claude")
    if not files or len(files)>MAX_PAGES:
        raise ClaudeBridgeError(f"Tryb testowy Claude obsługuje 1–{MAX_PAGES} stron")
    job_id=str(uuid.uuid4())
    root=BRIDGE_ROOT / "jobs"
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    job=root/job_id
    job.mkdir(mode=0o700)
    start=time.monotonic()
    try:
        for i,(image,mime) in enumerate(files,1):
            if mime!="image/jpeg" or not isinstance(image,bytes) or len(image)>MAX_IMAGE_BYTES:
                raise ClaudeBridgeError("Claude wymaga stron JPG do 8 MB")
            (job/f"page{i}.jpg").write_bytes(image)
        request={"job_id":job_id,"document_id":document_id,"dzial":dzial,"pages":len(files)}
        staging=job/"request.tmp"
        staging.write_text(json.dumps(request))
        staging.rename(job/"request.json")
        while time.monotonic()-start < timeout_seconds:
            result_file=job/"result.json"
            if result_file.exists():
                try:
                    result=json.loads(result_file.read_text(encoding="utf-8"))
                except (ValueError,OSError) as exc:
                    raise ClaudeBridgeError("Niepoprawna odpowiedź mostu Claude") from exc
                if result.get("error"):
                    raise ClaudeBridgeError("Claude: "+str(result["error"])[:240])
                return validate_ocr(result,len(files)),round(time.monotonic()-start,2)
            time.sleep(0.2)
        raise ClaudeBridgeError("Claude nie odpowiedział w limicie czasu (175 s). Sprawdź sesję Pro/limity.")
    finally:
        # The host daemon may still be processing; it handles disappearing job dirs gracefully.
        for path in job.glob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        try:
            job.rmdir()
        except OSError:
            pass
