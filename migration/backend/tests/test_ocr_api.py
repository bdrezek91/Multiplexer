"""Testy integracyjne Etapu 6: POST /ocr/recognize (dostawca Gemini zamockowany - bez sieci/kosztow)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.core.config import settings
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES


@pytest.fixture()
def gemini_key_configured():
    original = settings.gemini_api_key_free
    settings.gemini_api_key_free = "test-key"
    yield
    settings.gemini_api_key_free = original


def _fake_jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (100, 100), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


def _mock_recognize(response_text: str):
    return patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(return_value=response_text),
    )


def test_recognize_bez_tokenu_zwraca_401(client):
    files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
    r = client.post("/ocr/recognize", files=files)
    assert r.status_code == 401


def test_recognize_pusty_plik_zwraca_400(client, admin_headers, gemini_key_configured):
    files = {"plik": ("skan.jpg", b"", "image/jpeg")}
    r = client.post("/ocr/recognize", files=files, headers=admin_headers)
    assert r.status_code == 400


def test_recognize_sukces_rozpoznaje_i_dopasowuje_pozycje(
    client, admin_headers, gemini_key_configured, db_session, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    ai_response = (
        '{"numer_projektu": "35/06/26", "pozycje": ['
        '{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "ilosc_zuzyta": "1", "confidence": 98.5}'
        "]}"
    )
    files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
    with _mock_recognize(ai_response):
        r = client.post("/ocr/recognize", files=files, headers=admin_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["numer_projektu"] == "35/06/2026"
    assert body["rejected_count"] == 0
    assert len(body["pozycje"]) == 1

    item = body["pozycje"][0]
    assert item["rozpoznana_nazwa"] == "Grzejnik 1800W"
    assert item["ilosc_wydana"] == "1"
    assert item["off_form"] is True  # "1800W" to realna roznica wzgledem wiersza formularza
    assert item["match"]["kod"] == "GRZEJNIK 2000W"
    assert item["match"]["quality"] == "ok"


def test_recognize_odrzuca_niepoprawne_pozycje_i_liczy_je(
    client, admin_headers, gemini_key_configured, db_session, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    ai_response = '{"pozycje": [{"nazwa": "X"}, {"nazwa": "Peszel", "ilosc_wydana": "3"}]}'
    files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
    with _mock_recognize(ai_response):
        r = client.post("/ocr/recognize", files=files, headers=admin_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["rejected_count"] == 1  # "X" - nazwa za krotka
    assert len(body["pozycje"]) == 1
    assert body["pozycje"][0]["match"]["kod"] == "RURA KARBOWANA FI16"


def test_recognize_nie_json_zwraca_422(client, admin_headers, gemini_key_configured):
    with _mock_recognize("Przepraszam, nie moge pomoc z tym zadaniem."):
        files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
        r = client.post("/ocr/recognize", files=files, headers=admin_headers)
    assert r.status_code == 422


def test_recognize_bez_klucza_api_zwraca_502(client, admin_headers):
    original_free, original_paid = settings.gemini_api_key_free, settings.gemini_api_key_paid
    settings.gemini_api_key_free = None
    settings.gemini_api_key_paid = None
    try:
        files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
        r = client.post("/ocr/recognize", files=files, headers=admin_headers)
        assert r.status_code == 502
    finally:
        settings.gemini_api_key_free = original_free
        settings.gemini_api_key_paid = original_paid


def test_recognize_elektryk_ograniczony_do_przypisanych_magazynow(
    client, elektryk_headers, gemini_key_configured, db_session, baza_elektryka_json,
):
    """elektryk_user ma magazyny_dostepne=['Zabrze'] (patrz conftest.py) - ta sama regula RBAC co /match."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    files = {"plik": ("skan.jpg", _fake_jpeg_bytes(), "image/jpeg")}
    data = {"magazyn": "Czekanów"}
    with _mock_recognize('{"pozycje": []}'):
        r = client.post("/ocr/recognize", files=files, data=data, headers=elektryk_headers)
    assert r.status_code == 403
