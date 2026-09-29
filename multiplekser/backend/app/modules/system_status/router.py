from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import get_db
from app.modules.decision.jev_client import jev_enabled, jev_mode, jev_model
from app.modules.ocr.chain import classify_ocr_chain, default_ocr_chain, quantity_verification_chain
from app.modules.ocr.cooldown import get_ocr_cooldown_store
from app.modules.users import require_admin
from app.modules.users.models import UserModel

router = APIRouter(prefix="/system", tags=["system"])
_BACKUP_LAST_SUCCESS = Path("/var/backups/multiplekser/LAST_SUCCESS")


class ServiceStatus(BaseModel):
    ok: bool
    detail: str | None = None


class WorkerStatus(BaseModel):
    online: bool
    node: str | None = None


class QueueStatus(BaseModel):
    length: int


class CooldownStatus(BaseModel):
    label: str
    model: str
    remaining_seconds: int


class RecentDocumentTiming(BaseModel):
    document_id: str
    numer_projektu: str | None
    created_at: datetime
    duration_ms: int | None


class AlertOut(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class SystemStatusOut(BaseModel):
    generated_at: datetime
    overall: Literal["ok", "warning", "error"]
    services: dict[str, ServiceStatus]
    workers: dict[str, WorkerStatus]
    queues: dict[str, QueueStatus]
    backup_last_success: datetime | None
    backup_age_hours: float | None
    backup_ok: bool
    jev_enabled: bool
    jev_mode: str
    jev_model: str
    cooldowns: list[CooldownStatus]
    avg_last10_ms: int | None
    last_document_ms: int | None
    recent_documents: list[RecentDocumentTiming]
    documents_error_24h: int
    ai_failed_events_24h: int
    alerts: list[AlertOut]


def _timing_from_trace(trace: list[dict] | None, stage: str) -> int | None:
    for event in reversed(trace or []):
        if event.get("stage") == stage and event.get("duration_ms") is not None:
            try:
                return max(0, int(event["duration_ms"]))
            except (TypeError, ValueError):
                return None
    return None


def _backup_status(path: Path = _BACKUP_LAST_SUCCESS) -> tuple[datetime | None, float | None, bool]:
    try:
        stat = path.stat()
    except OSError:
        return None, None, False
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - modified).total_seconds() / 3600.0)
    return modified, round(age_hours, 1), age_hours <= 36.0


def _build_alerts(
    *,
    services: dict[str, ServiceStatus],
    workers: dict[str, WorkerStatus],
    queues: dict[str, QueueStatus],
    backup_ok: bool,
    backup_age_hours: float | None,
    avg_last10_ms: int | None,
    documents_error_24h: int,
) -> list[AlertOut]:
    alerts: list[AlertOut] = []

    for name, state in services.items():
        if not state.ok:
            alerts.append(AlertOut(
                severity="error",
                code=f"service_{name}_down",
                message=f"{name}: usługa niedostępna" + (f" ({state.detail})" if state.detail else ""),
            ))

    for name, state in workers.items():
        if not state.online:
            alerts.append(AlertOut(
                severity="error",
                code=f"worker_{name}_offline",
                message=f"Worker {name} jest OFFLINE.",
            ))

    ocr_queue = queues.get("ocr", QueueStatus(length=0)).length
    if ocr_queue > 3:
        alerts.append(AlertOut(
            severity="warning",
            code="ocr_queue_high",
            message=f"Kolejka OCR ma {ocr_queue} oczekujące zadania.",
        ))

    background_queue = queues.get("background", QueueStatus(length=0)).length
    if background_queue > 10:
        alerts.append(AlertOut(
            severity="warning",
            code="background_queue_high",
            message=f"Kolejka background ma {background_queue} oczekujących zadań.",
        ))

    if not backup_ok:
        age_text = "brak poprawnego backupu" if backup_age_hours is None else f"backup ma {backup_age_hours:.1f} h"
        alerts.append(AlertOut(
            severity="error",
            code="backup_stale",
            message=f"Backup Multipleksera wymaga uwagi: {age_text}.",
        ))

    if avg_last10_ms is not None and avg_last10_ms > 30_000:
        alerts.append(AlertOut(
            severity="warning",
            code="ocr_slow",
            message=f"Średni czas ostatnich wydawek to {avg_last10_ms / 1000:.1f} s (>30 s).",
        ))

    if documents_error_24h > 0:
        alerts.append(AlertOut(
            severity="warning",
            code="documents_error_24h",
            message=f"Dokumenty zakończone błędem w ostatnich 24 h: {documents_error_24h}.",
        ))

    return alerts


def _service_checks(session: Session, redis_client: Redis) -> dict[str, ServiceStatus]:
    services: dict[str, ServiceStatus] = {
        "Backend": ServiceStatus(ok=True),
    }

    try:
        session.execute(text("SELECT 1"))
        services["PostgreSQL"] = ServiceStatus(ok=True)
    except Exception as exc:
        session.rollback()
        services["PostgreSQL"] = ServiceStatus(ok=False, detail=type(exc).__name__)

    try:
        redis_client.ping()
        services["Redis"] = ServiceStatus(ok=True)
    except Exception as exc:
        services["Redis"] = ServiceStatus(ok=False, detail=type(exc).__name__)

    try:
        client = boto3.client(
            "s3",
            endpoint_url=settings.minio_endpoint_url,
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            region_name="us-east-1",
            config=BotoConfig(connect_timeout=1, read_timeout=1, retries={"max_attempts": 1}),
        )
        client.head_bucket(Bucket=settings.minio_bucket)
        services["MinIO"] = ServiceStatus(ok=True)
    except Exception as exc:
        services["MinIO"] = ServiceStatus(ok=False, detail=type(exc).__name__)

    return services


def _worker_status() -> dict[str, WorkerStatus]:
    result = {
        "OCR": WorkerStatus(online=False),
        "Background": WorkerStatus(online=False),
    }
    try:
        pong = celery_app.control.inspect(timeout=1.0).ping() or {}
    except Exception:
        pong = {}

    for node in pong:
        if node.startswith("ocr@"):
            result["OCR"] = WorkerStatus(online=True, node=node)
        elif node.startswith("background@"):
            result["Background"] = WorkerStatus(online=True, node=node)
    return result


def _cooldowns() -> list[CooldownStatus]:
    store = get_ocr_cooldown_store()
    unique: dict[str, str] = {}
    for step in [*default_ocr_chain(), *classify_ocr_chain(), *quantity_verification_chain()]:
        unique.setdefault(step.label, step.model)

    rows = []
    for label, model in unique.items():
        remaining = store.remaining_seconds(label)
        if remaining > 0:
            rows.append(CooldownStatus(label=label, model=model, remaining_seconds=remaining))
    rows.sort(key=lambda row: row.remaining_seconds, reverse=True)
    return rows


def _recent_stats(session: Session) -> tuple[list[RecentDocumentTiming], int | None, int | None, int, int]:
    rows = session.execute(text("""
        SELECT id::text AS id, numer_projektu, created_at, ai_trace
        FROM document
        WHERE status='done'
        ORDER BY created_at DESC
        LIMIT 10
    """)).mappings().all()

    recent: list[RecentDocumentTiming] = []
    durations: list[int] = []
    for row in rows:
        duration = _timing_from_trace(row["ai_trace"] or [], "timing_to_done")
        if duration is not None:
            durations.append(duration)
        recent.append(RecentDocumentTiming(
            document_id=row["id"],
            numer_projektu=row["numer_projektu"],
            created_at=row["created_at"],
            duration_ms=duration,
        ))

    avg = round(sum(durations) / len(durations)) if durations else None
    last = recent[0].duration_ms if recent else None

    errors = int(session.execute(text("""
        SELECT count(*) FROM document
        WHERE status='error' AND created_at >= now() - interval '24 hours'
    """)).scalar_one())

    traces = session.execute(text("""
        SELECT ai_trace FROM document
        WHERE created_at >= now() - interval '24 hours'
    """)).scalars().all()
    ai_failed = sum(
        1
        for trace in traces
        for event in (trace or [])
        if event.get("status") == "failed"
    )
    return recent, avg, last, errors, ai_failed


@router.get("/status", response_model=SystemStatusOut)
def get_system_status(
    session: Session = Depends(get_db),
    _admin: UserModel = Depends(require_admin),
):
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

    services = _service_checks(session, redis_client)
    workers = _worker_status()

    queues: dict[str, QueueStatus] = {}
    for queue in ("ocr", "background"):
        try:
            queues[queue] = QueueStatus(length=int(redis_client.llen(queue)))
        except Exception:
            queues[queue] = QueueStatus(length=-1)

    backup_last_success, backup_age_hours, backup_ok = _backup_status()
    try:
        recent, avg_last10_ms, last_document_ms, documents_error_24h, ai_failed_events_24h = _recent_stats(session)
    except Exception:
        session.rollback()
        recent, avg_last10_ms, last_document_ms = [], None, None
        documents_error_24h, ai_failed_events_24h = 0, 0
    cooldowns = _cooldowns()

    alerts = _build_alerts(
        services=services,
        workers=workers,
        queues=queues,
        backup_ok=backup_ok,
        backup_age_hours=backup_age_hours,
        avg_last10_ms=avg_last10_ms,
        documents_error_24h=documents_error_24h,
    )
    overall: Literal["ok", "warning", "error"] = "ok"
    if any(alert.severity == "error" for alert in alerts):
        overall = "error"
    elif alerts:
        overall = "warning"

    return SystemStatusOut(
        generated_at=datetime.now(timezone.utc),
        overall=overall,
        services=services,
        workers=workers,
        queues=queues,
        backup_last_success=backup_last_success,
        backup_age_hours=backup_age_hours,
        backup_ok=backup_ok,
        jev_enabled=jev_enabled(),
        jev_mode=jev_mode(),
        jev_model=jev_model(),
        cooldowns=cooldowns,
        avg_last10_ms=avg_last10_ms,
        last_document_ms=last_document_ms,
        recent_documents=recent,
        documents_error_24h=documents_error_24h,
        ai_failed_events_24h=ai_failed_events_24h,
        alerts=alerts,
    )
