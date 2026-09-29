"""Pomocnicza telemetryka czasu dla taskow dokumentow."""
from __future__ import annotations

import time
from datetime import datetime, timezone

def _timing_event(stage: str, duration_ms: int, reason: str | None = None) -> dict[str, object]:
    return {
        "status": "completed",
        "stage": stage,
        "provider": None,
        "model": None,
        "label": None,
        "reason": reason,
        "step": None,
        "total_steps": None,
        "duration_ms": max(0, int(duration_ms)),
        "attempt": None,
        "target": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _queue_wait_ms(created_at: datetime | None) -> int | None:
    if created_at is None:
        return None
    try:
        value = created_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0, round((datetime.now(timezone.utc) - value).total_seconds() * 1000))
    except Exception:
        return None


def _background_queue_wait_ms(document) -> int | None:
    for event in reversed(list(document.ai_trace or [])):
        if event.get("stage") != "full_document_verification" or event.get("status") != "queued":
            continue
        raw = event.get("created_at")
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return max(0, round((datetime.now(timezone.utc) - value).total_seconds() * 1000))
        except (TypeError, ValueError):
            return None
    return None
