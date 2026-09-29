from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.modules.documents.tasks import _background_queue_wait_ms, _queue_wait_ms, _timing_event


def test_timing_event_ma_staly_format():
    event = _timing_event('timing_ocr_matcher', 1234)
    assert event['status'] == 'completed'
    assert event['stage'] == 'timing_ocr_matcher'
    assert event['duration_ms'] == 1234
    assert event['provider'] is None
    assert event['model'] is None
    assert event['created_at']


def test_queue_wait_ms_liczy_czas_od_utworzenia_dokumentu():
    created = datetime.now(timezone.utc) - timedelta(seconds=2)
    wait = _queue_wait_ms(created)
    assert wait is not None
    assert 1500 <= wait <= 3000


def test_background_queue_wait_ms_bierze_najnowszy_event_queued():
    old = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    recent = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
    document = SimpleNamespace(ai_trace=[
        {'stage': 'full_document_verification', 'status': 'queued', 'created_at': old},
        {'stage': 'classification', 'status': 'selected', 'created_at': recent},
        {'stage': 'full_document_verification', 'status': 'queued', 'created_at': recent},
    ])
    wait = _background_queue_wait_ms(document)
    assert wait is not None
    assert 1500 <= wait <= 3000


def test_background_queue_wait_ms_bez_queued_zwraca_none():
    document = SimpleNamespace(ai_trace=[])
    assert _background_queue_wait_ms(document) is None
