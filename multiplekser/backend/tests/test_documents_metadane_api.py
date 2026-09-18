"""Testy: odczyt pracownika/numeru plomby-rozdzielni z naglowka przez OCR i PATCH
/documents/{id}/metadane - reczna korekta tych pol po zakonczonym OCR (2026-09-17, na zyczenie
uzytkownika). W przeciwienstwie do PATCH .../magazyn te pola sa tylko informacyjne, wiec
zmiana NIE wywoluje ponownego dopasowania pozycji."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import run_ocr_task
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules


def _fake_jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


def _mock_recognize(response_text: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=response_text))


def _create_done_document(db_session, user, ai_response: str) -> str:
    key = f"documents/test/{user.id}-{ai_response[:8]}.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    with _mock_recognize(ai_response):
        run_ocr_task(str(document.id), db_session)
    return str(document.id)


def test_ocr_odczytuje_pracownika_i_numer_plomby_z_naglowka(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = (
        '{"pracownik": "Jan Kowalski", "numer_plomby": "12345", "pozycje": '
        '[{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.get(f"/documents/{doc_id}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["pracownik"] == "Jan Kowalski"
    assert r.json()["numer_plomby"] == "12345"


def test_ocr_bez_pracownika_i_numeru_plomby_zwraca_null(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.get(f"/documents/{doc_id}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["pracownik"] is None
    assert r.json()["numer_plomby"] is None


def test_patch_metadane_poprawia_pracownika(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = (
        '{"pracownik": "Jan Kowalski", "pozycje": '
        '[{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/metadane", json={"pracownik": "Anna Nowak"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pracownik"] == "Anna Nowak"
    assert body["numer_plomby"] is None  # pole nieobecne w body - bez zmian


def test_patch_metadane_null_kasuje_wartosc(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = (
        '{"numer_plomby": "12345", "pozycje": '
        '[{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/metadane", json={"numer_plomby": None}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["numer_plomby"] is None


def test_patch_metadane_nie_zmienia_dopasowania_pozycji(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Kontrast wobec PATCH .../magazyn - te pola sa tylko informacyjne, wiec zadnej pozycji nie
    dopasowuje sie ponownie."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    before = doc_repo.get_document(db_session, doc_id).items[0].match_kod

    r = client.patch(f"/documents/{doc_id}/metadane", json={"pracownik": "Anna Nowak"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["match_kod"] == before


def test_patch_metadane_poprawia_numer_projektu(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = (
        '{"numer_projektu": "113/06/2026", "pozycje": '
        '[{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/metadane", json={"numer_projektu": "999/07/2026"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["numer_projektu"] == "999/07/2026"
    assert body["pracownik"] is None  # pole nieobecne w body - bez zmian


def test_patch_metadane_nieistniejacy_dokument_zwraca_404(client, admin_headers):
    r = client.patch(
        "/documents/00000000-0000-0000-0000-000000000000/metadane",
        json={"pracownik": "Anna Nowak"}, headers=admin_headers,
    )
    assert r.status_code == 404


def test_patch_metadane_cudzy_dokument_zwraca_403(
    client, db_session, admin_user, magazynier_headers, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/metadane", json={"pracownik": "Anna Nowak"}, headers=magazynier_headers)
    assert r.status_code == 403


def test_patch_metadane_wymaga_zalogowania(client, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/metadane", json={"pracownik": "Anna Nowak"})
    assert r.status_code == 401
