"""Testy decision/tasks.py (Jev shadow jako osobne zadanie Celery, 2026-09-29). Sprawdzaja
przede wszystkim: zero wplywu na dokument/pozycje w bazie, fail-open na blad TypeSafe, i
ze zadanie jest calkowitym no-opem gdy JEV_ENABLED=false (domyslnie)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.modules.decision.tasks import dispatch_jev_shadow_task, run_jev_shadow_for_document
from app.modules.documents import repository
from app.modules.documents.models import DocumentModel

FIXTURES = Path(__file__).parent / "fixtures"


def _make_done_document(db_session, admin_user, storage):
    document = repository.create_document(
        db_session, user_id=admin_user.id, file_key="k1", mime="image/jpeg",
        original_filename="f.jpg",
    )
    db_session.commit()
    repository.mark_done(
        db_session, document,
        numer_projektu=None, used_provider="gemini", rejected_count=0,
        items=[
            {
                "rozpoznana_nazwa": "Różnicówka niemiecka 1 fazowa 40A",
                "ilosc_wydana": None, "ilosc_zuzyta": 1.0, "ilosc_finalna": 1.0,
                "match_quality": "ok", "match_score": 0.56,
                "off_form": False, "needs_review": False, "form_note": None,
                "uwagi": None, "confidence": 0.9, "matched_product_id": None,
                "match_kod": "RÓŻNICÓWKA NIEMIECKA CDS240D",
                "match_nazwa": "Różnicówka niemiecka CDS240D", "match_jm": "SZT",
                "ilosc_z_dodatkowej_kontroli": False,
            },
        ],
        dzial="elektryka", dzial_confidence=0.99,
    )
    db_session.commit()
    return document


def _jev_ok_response(choice: str, confidence: float = 0.9):
    return httpx.Response(200, request=httpx.Request("POST", "https://api.typesafe.ai/v1/systemone"), json={
        "model": "jev-1.13.0",
        "answers": {"produkt": {"type": "choice", "choice": choice, "confidence": confidence,
                                  "probabilities": {choice: confidence}}},
        "usage": {"input_tokens": 5, "output_tokens": 2},
    })


def test_dispatch_no_op_gdy_jev_wylaczony(monkeypatch, db_session, admin_user, mocked_storage):
    monkeypatch.setenv("JEV_ENABLED", "false")
    document = _make_done_document(db_session, admin_user, mocked_storage)

    with patch("app.modules.decision.tasks.process_jev_shadow.delay") as delay_mock:
        dispatch_jev_shadow_task(str(document.id))

    delay_mock.assert_not_called()


def test_run_nie_zmienia_dokumentu_w_bazie(monkeypatch, db_session, admin_user, mocked_storage):
    """Krytyczne: bez wzgledu na to co zwroci Jev, DocumentModel/DocumentItemModel w bazie
    pozostaja niezmienione - to jest istota trybu shadow."""
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    document = _make_done_document(db_session, admin_user, mocked_storage)
    original_kod = document.items[0].match_kod

    fake = _jev_ok_response("C0", confidence=0.42)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        run_jev_shadow_for_document(str(document.id), db_session)

    db_session.expire_all()
    refreshed = db_session.get(DocumentModel, document.id)
    assert refreshed.items[0].match_kod == original_kod
    assert refreshed.status == "done"


def test_run_fail_open_na_blad_typesafe(monkeypatch, db_session, admin_user, mocked_storage):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    document = _make_done_document(db_session, admin_user, mocked_storage)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))):
        # Nie moze podniesc wyjatku - to jest sedno fail-open dla calego dokumentu.
        run_jev_shadow_for_document(str(document.id), db_session)


def test_run_pomija_hydraulike(monkeypatch, db_session, admin_user, mocked_storage):
    """Diagnostyka/query_features sa dzis tylko dla Elektryki - dla Hydrauliki zadanie
    powinno zakonczyc sie natychmiast, bez zadnego wywolania do TypeSafe."""
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    document = repository.create_document(
        db_session, user_id=admin_user.id, file_key="k2", mime="image/jpeg",
        original_filename="f2.jpg",
    )
    db_session.commit()
    repository.mark_done(
        db_session, document,
        numer_projektu=None, used_provider="gemini", rejected_count=0,
        items=[{
            "rozpoznana_nazwa": "Zawór kulowy 1/2", "ilosc_wydana": None, "ilosc_zuzyta": 1.0,
            "ilosc_finalna": 1.0, "match_quality": "ok", "match_score": 0.9,
            "off_form": False, "needs_review": False, "form_note": None, "uwagi": None,
            "confidence": 0.9, "matched_product_id": None, "match_kod": "ZAWÓR KULOWY 1/2",
            "match_nazwa": "Zawór kulowy 1/2", "match_jm": "SZT", "ilosc_z_dodatkowej_kontroli": False,
        }],
        dzial="hydraulika", dzial_confidence=0.99,
    )
    db_session.commit()

    with patch("httpx.AsyncClient.post", new=AsyncMock()) as post_mock:
        run_jev_shadow_for_document(str(document.id), db_session)

    post_mock.assert_not_called()
