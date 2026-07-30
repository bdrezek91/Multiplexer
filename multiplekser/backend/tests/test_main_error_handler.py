"""Test globalnego handlera bledow (Etap "quick winy" - 2026-07-30). Sprawdza, ze
nieprzewidziany wyjatek (nie swiadome HTTPException z routera) konczy sie czystym JSON-em
{"detail": "..."} zamiast surowego 500 bez spojnego ksztaltu - patrz app/main.py,
unhandled_exception_handler.

Uzywa lokalnego TestClient z raise_server_exceptions=False - fixture `client` z conftest.py
celowo tego nie robi (domyslne raise_server_exceptions=True daje czytelny traceback Pythona
przy prawdziwym bledzie w innych testach), wiec normalnie wyjatek przechodzacy przez handler
i tak zostalby ponownie podniesiony przez sam TestClient, zanim zdazylibysmy zobaczyc
odpowiedz JSON."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app


def test_nieoczekiwany_wyjatek_zwraca_czysty_json_500(db_session, admin_headers):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        lenient_client = TestClient(app, raise_server_exceptions=False)
        with patch("app.main.Catalog.from_db", side_effect=RuntimeError("symulowana awaria")):
            r = lenient_client.post(
                "/match",
                json={"query": "cokolwiek"},
                headers=admin_headers,
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 500
    assert r.json() == {"detail": "Wystąpił nieoczekiwany błąd serwera (RuntimeError)"}
