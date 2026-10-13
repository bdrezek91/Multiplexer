"""Private, token-free usage ledger for the Claude Pro bridge.

Tracks only OCR job counts, pages, duration, metered model tokens where the
official CLI exposes them, and category of failures. NOT Claude subscription
remaining quota; only Anthropic's own account Usage screen knows that.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

ROOT = Path("/var/lib/multiplekser-claude-bridge")
HISTORY = ROOT / "usage_history.jsonl"
SUMMARY = ROOT / "usage.json"
MAX_EVENTS = 3000


def error_kind(message: str) -> str:
    s = str(message).lower()
    if any(x in s for x in (
        "rate limit", "rate_limit", "usage limit", "usage_limit",
        "limit_cooldown", "out of extra usage", "capacity limit",
        "you've reached", "you have reached", "quota", "limit reached",
        "weekly limit", "5-hour limit", "five-hour limit",
        "resets at", "too many requests",
    )):
        return "limit"
    if any(x in s for x in ("oauth", "login expired", "authentication failed", "unauthorized", "not logged in")):
        return "auth"
    if "timeout" in s or "timed out" in s:
        return "timeout"
    return "failed"


def usage_from_event(result: dict) -> dict:
    """Parse actual reported tokens if available. Never treat them as quota %."""
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return {}
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    values = {}
    for k in keys:
        n = usage.get(k)
        if type(n) is int and n >= 0:
            values[k] = n
    return values


def _load() -> list[dict]:
    if not HISTORY.exists():
        return []
    records = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines()[-MAX_EVENTS:]:
        try:
            row = json.loads(line)
            if isinstance(row, dict) and "epoch" in row and "status" in row:
                records.append(row)
        except ValueError:
            continue
    return records


def _summarize(events: list[dict]) -> dict:
    now = time.time()
    done = [r for r in events if r.get("status") == "done"]
    day = [r for r in done if r.get("epoch", 0) >= now - 86400]
    week = [r for r in done if r.get("epoch", 0) >= now - 7 * 86400]
    last = events[-1] if events else None
    failures = [r for r in events if r.get("status") != "done"]
    durations = [r.get("seconds", 0) for r in done if isinstance(r.get("seconds"), (int, float))]
    return {
        "available": True,
        "plan": "Claude Pro (owner OAuth)",
        "model": "sonnet",
        "effort": "low",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(events),
        "done": len(done),
        "failed": len(failures),
        "pages_done": sum(int(r.get("pages", 0)) for r in done),
        "rows_done": sum(int(r.get("rows", 0)) for r in done),
        "jobs_24h": len(day),
        "pages_24h": sum(int(r.get("pages", 0)) for r in day),
        "jobs_7d": len(week),
        "pages_7d": sum(int(r.get("pages", 0)) for r in week),
        "avg_seconds": round(sum(durations)/len(durations), 1) if durations else None,
        "last_status": last.get("status") if last else None,
        "last_error_kind": failures[-1].get("error_kind") if failures else None,
        "last_error_at": failures[-1].get("at") if failures else None,
        "last_job_at": last.get("at") if last else None,
        "subscription_remaining": None,  # official quota percentage not exposed by CLI
    }


def record(*, status: str, pages: int, seconds: float, rows: int=0,
           error: str="", tokens: dict | None=None) -> None:
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    event = {
        "epoch": time.time(),
        "at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "pages": pages,
        "rows": rows,
        "seconds": round(seconds, 2),
    }
    if status != "done":
        event["error_kind"] = error_kind(error)
    if tokens:
        event["tokens"] = tokens
    # Single host service writes sequentially; never expose customer names or OCR content.
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(HISTORY, 0o600)
    events = _load()
    output = _summarize(events)
    temp = SUMMARY.with_suffix(".tmp")
    temp.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        # The backend API container runs as the same app UID as the worker.
        app_stat = (ROOT / "jobs").stat()
        os.chown(temp, 0, app_stat.st_gid)
    except OSError:
        pass
    temp.chmod(0o640)
    temp.replace(SUMMARY)


def heartbeat() -> None:
    """Indicates host bridge daemon liveness; no secrets, no customer content."""
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp=ROOT/"heartbeat.tmp"
    temp.write_text(json.dumps({"epoch":time.time()}),encoding="utf-8")
    try:
        owner=(ROOT/"jobs").stat()
        os.chown(temp,0,owner.st_gid)
    except OSError:
        pass
    temp.chmod(0o640)
    temp.replace(ROOT/"heartbeat.json")
