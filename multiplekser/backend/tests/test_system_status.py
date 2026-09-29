import os
from datetime import datetime, timedelta, timezone

from app.modules.system_status.router import (
    QueueStatus,
    ServiceStatus,
    WorkerStatus,
    _backup_status,
    _build_alerts,
    _timing_from_trace,
)


def test_timing_from_trace_bierze_najnowsza_metryke():
    trace = [
        {"stage": "timing_to_done", "duration_ms": 12000},
        {"stage": "timing_to_done", "duration_ms": 9000},
    ]
    assert _timing_from_trace(trace, "timing_to_done") == 9000


def test_backup_status_swiezy(tmp_path):
    path = tmp_path / "LAST_SUCCESS"
    path.write_text("20260929T050000Z")
    when = datetime.now(timezone.utc) - timedelta(hours=2)
    os.utime(path, (when.timestamp(), when.timestamp()))

    last, age, ok = _backup_status(path)

    assert last is not None
    assert age is not None
    assert 1.5 <= age <= 2.5
    assert ok is True


def test_backup_status_stary(tmp_path):
    path = tmp_path / "LAST_SUCCESS"
    path.write_text("old")
    when = datetime.now(timezone.utc) - timedelta(hours=40)
    os.utime(path, (when.timestamp(), when.timestamp()))

    _last, age, ok = _backup_status(path)

    assert age is not None and age >= 39
    assert ok is False


def test_alerty_wykrywaja_worker_queue_backup_i_wolny_ocr():
    alerts = _build_alerts(
        services={
            "Backend": ServiceStatus(ok=True),
            "PostgreSQL": ServiceStatus(ok=True),
            "Redis": ServiceStatus(ok=True),
            "MinIO": ServiceStatus(ok=True),
        },
        workers={
            "OCR": WorkerStatus(online=False),
            "Background": WorkerStatus(online=True, node="background@test"),
        },
        queues={
            "ocr": QueueStatus(length=4),
            "background": QueueStatus(length=0),
        },
        backup_ok=False,
        backup_age_hours=40.0,
        avg_last10_ms=31_000,
        documents_error_24h=1,
    )

    codes = {alert.code for alert in alerts}
    assert "worker_OCR_offline" in codes
    assert "ocr_queue_high" in codes
    assert "backup_stale" in codes
    assert "ocr_slow" in codes
    assert "documents_error_24h" in codes


def test_brak_alertow_przy_zdrowym_systemie():
    alerts = _build_alerts(
        services={
            "Backend": ServiceStatus(ok=True),
            "PostgreSQL": ServiceStatus(ok=True),
            "Redis": ServiceStatus(ok=True),
            "MinIO": ServiceStatus(ok=True),
        },
        workers={
            "OCR": WorkerStatus(online=True, node="ocr@test"),
            "Background": WorkerStatus(online=True, node="background@test"),
        },
        queues={
            "ocr": QueueStatus(length=0),
            "background": QueueStatus(length=0),
        },
        backup_ok=True,
        backup_age_hours=1.0,
        avg_last10_ms=14_000,
        documents_error_24h=0,
    )
    assert alerts == []
