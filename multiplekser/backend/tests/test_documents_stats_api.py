"""Testy: GET /documents/stats/summary - licznik przerobionych dokumentow per uzytkownik dla
panelu administratora, zestawiony z zaoszczedzonym czasem/pieniedzmi wzgledem recznego
wprowadzania wydawki (2026-09-21, na zyczenie uzytkownika)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import run_ocr_task
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules

_OK_RESPONSE = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'


def _fake_jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


def _mock_recognize(response_text: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=response_text))


def _create_document(db_session, user, *, status: str = "done") -> str:
    key = f"documents/test/{user.id}-{uuid_suffix()}.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    if status == "done":
        with _mock_recognize(_OK_RESPONSE):
            run_ocr_task(str(document.id), db_session)
    elif status == "error":
        doc_repo.mark_error(db_session, document, "blad testowy")
    return str(document.id)


def uuid_suffix() -> str:
    import uuid

    return str(uuid.uuid4())[:8]


def test_stats_liczy_tylko_gotowe_dokumenty_i_wylicza_oszczednosci(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    _create_document(db_session, admin_user, status="done")
    _create_document(db_session, admin_user, status="done")
    _create_document(db_session, admin_user, status="error")

    r = client.get("/documents/stats/summary", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(row for row in body["per_user"] if row["email"] == admin_user.email)
    assert row["dokumenty"] == 2  # dokument "error" NIE liczy sie
    assert row["minuty_zaoszczedzone"] == 16
    assert row["pieniadze_zaoszczedzone"] == round(16 / 60 * 55.0, 2)
    assert body["razem_dokumenty"] == 2
    assert body["minuty_na_dokument"] == 8
    assert body["stawka_pln_za_h"] == 55.0


def test_stats_wymaga_roli_admin(
    client, db_session, admin_user, magazynier_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    _create_document(db_session, admin_user, status="done")

    r = client.get("/documents/stats/summary", headers=magazynier_headers)
    assert r.status_code == 403


def test_stats_wymaga_zalogowania(client):
    r = client.get("/documents/stats/summary")
    assert r.status_code == 401


def test_stats_bez_zadnych_dokumentow_zwraca_puste_zestawienie(client, admin_headers):
    r = client.get("/documents/stats/summary", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["per_user"] == []
    assert body["razem_dokumenty"] == 0
    assert body["razem_minuty_zaoszczedzone"] == 0
    assert body["razem_pieniadze_zaoszczedzone"] == 0
