"""Regresja routingu Celery: zadania blokujace uzytkownika nie moga dzielic kolejki z tlem."""

from app.core.celery_app import celery_app


def test_celery_ma_osobne_kolejki_ocr_i_background():
    routes = celery_app.conf.task_routes

    assert celery_app.conf.task_default_queue == "ocr"
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert routes["documents.process_ocr"]["queue"] == "ocr"
    assert routes["documents.full_document_verification"]["queue"] == "background"
    assert routes["decision.jev_shadow"]["queue"] == "background"


def test_taski_sa_zarejestrowane_po_imporcie_modulow():
    import app.modules.documents.tasks  # noqa: F401
    import app.modules.decision.tasks  # noqa: F401

    assert "documents.process_ocr" in celery_app.tasks
    assert "documents.full_document_verification" in celery_app.tasks
    assert "decision.jev_shadow" in celery_app.tasks
