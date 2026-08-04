"""Testy Kroku Hydraulika-6: PATCH /documents/{id}/magazyn - zmiana magazynu po zakonczonym
OCR, z ponownym dopasowaniem wszystkich pozycji (R5: podstawienie kodu zalezy od magazynu)."""
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


def _create_done_document(db_session, admin_user, ai_response: str, magazyn=None) -> str:
    key = f"documents/test/{admin_user.id}-{ai_response[:8]}.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg",
        original_filename="skan.jpg", magazyn=magazyn,
    )
    with _mock_recognize(ai_response):
        run_ocr_task(str(document.id), db_session)
    return str(document.id)


def test_zmiana_magazynu_podmienia_kod_wg_wariantu_magazynowego(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """BEZPIECZNIK 25A NIEMIECKI ma wariant magazynowy (1P) dla Czekanowa - patrz test_generate,
    test_products_api. Dokument uploadowany BEZ magazynu, potem magazyn ustawiany po fakcie."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Bezpiecznik 25A Niemiecki", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    before = doc_repo.get_document(db_session, doc_id)
    assert before.items[0].match_kod == "BEZPIECZNIK 25A NIEMIECKI"  # bez magazynu, bez substytucji

    r = client.patch(f"/documents/{doc_id}/magazyn", json={"magazyn": "Czekanów"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["magazyn"] == "Czekanów"
    assert body["items"][0]["match_kod"] == "BEZPIECZNIK 25A NIEMIECKI 1P"


def test_zmiana_magazynu_na_pusty_cofa_substytucje(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Bezpiecznik 25A Niemiecki", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response, magazyn="Czekanów")
    assert doc_repo.get_document(db_session, doc_id).items[0].match_kod == "BEZPIECZNIK 25A NIEMIECKI 1P"

    r = client.patch(f"/documents/{doc_id}/magazyn", json={"magazyn": None}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["magazyn"] is None
    assert r.json()["items"][0]["match_kod"] == "BEZPIECZNIK 25A NIEMIECKI"


def test_zmiana_magazynu_dziala_dla_hydrauliki(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    classify_response = '{"dzial":"hydraulika","confidence":90.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 95}]}'
    key = f"documents/test/{admin_user.id}-hydraulika-mag.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(str(document.id), db_session)

    r = client.patch(f"/documents/{document.id}/magazyn", json={"magazyn": "Zabrze"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["magazyn"] == "Zabrze"
    assert r.json()["items"][0]["match_kod"] == "BOJLER 80 L"


def test_zmiana_magazynu_nieistniejacy_dokument_zwraca_404(client, admin_headers):
    r = client.patch("/documents/00000000-0000-0000-0000-000000000000/magazyn", json={"magazyn": "Zabrze"}, headers=admin_headers)
    assert r.status_code == 404


def test_zmiana_magazynu_cudzy_dokument_zwraca_403(
    client, db_session, admin_user, magazynier_headers, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(f"/documents/{doc_id}/magazyn", json={"magazyn": "Zabrze"}, headers=magazynier_headers)
    assert r.status_code == 403


def test_zmiana_magazynu_magazynier_ograniczony_do_przypisanych_magazynow(
    client, db_session, magazynier_user, magazynier_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """magazynier_user ma dostep tylko do Zabrza (patrz conftest.py) - proba ustawienia Czekanowa
    (do ktorego nie ma dostepu) musi zostac odrzucona."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    key = f"documents/test/{magazynier_user.id}-own.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=magazynier_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    with _mock_recognize(ai_response):
        run_ocr_task(str(document.id), db_session)

    r = client.patch(f"/documents/{document.id}/magazyn", json={"magazyn": "Czekanów"}, headers=magazynier_headers)
    assert r.status_code == 403
