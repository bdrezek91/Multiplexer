"""Testy integracyjne Etapu 7: POST/GET /documents. process_ocr_document.delay() jest zamockowane
(no-op) - logika przetwarzania jest juz w pelni pokryta w test_documents_task.py; tu testujemy
kontrakt API (upload do storage, zapis wiersza, RBAC wlasciciela/magazynu, statusy HTTP)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.tasks import run_ocr_task
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules


def _fake_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="green").save(buf, format="JPEG")
    return buf.getvalue()


def _no_delay():
    return patch("app.modules.documents.router.process_ocr_document.delay")


def test_create_document_bez_tokenu_zwraca_401(client, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    r = client.post("/documents", files=files)
    assert r.status_code == 401


def test_create_document_pusty_plik_zwraca_400(client, admin_headers, mocked_storage):
    files = {"plik": ("skan.jpg", b"", "image/jpeg")}
    with _no_delay():
        r = client.post("/documents", files=files, headers=admin_headers)
    assert r.status_code == 400


def test_create_document_sukces_zwraca_202_i_zleca_zadanie(client, admin_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay() as mock_delay:
        r = client.post("/documents", files=files, headers=admin_headers)

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["id"]
    mock_delay.assert_called_once_with(body["id"])


def test_get_document_zwraca_status_i_wlasciciela_widzi_swoj_dokument(client, admin_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=admin_headers).json()

    r = client.get(f"/documents/{created['id']}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert body["original_filename"] == "skan.jpg"
    assert body["items"] == []


def test_get_document_nieistniejacego_zwraca_404(client, admin_headers):
    r = client.get("/documents/00000000-0000-0000-0000-000000000000", headers=admin_headers)
    assert r.status_code == 404


def test_get_document_cudzy_zwraca_403_dla_nie_admina(client, admin_headers, elektryk_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=admin_headers).json()

    r = client.get(f"/documents/{created['id']}", headers=elektryk_headers)
    assert r.status_code == 403


def test_get_document_admin_widzi_cudzy_dokument(client, admin_headers, elektryk_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=elektryk_headers).json()

    r = client.get(f"/documents/{created['id']}", headers=admin_headers)
    assert r.status_code == 200


def test_list_documents_nieadmin_widzi_tylko_swoje(client, admin_headers, elektryk_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        client.post("/documents", files=files, headers=admin_headers)
        client.post("/documents", files=files, headers=elektryk_headers)

    r = client.get("/documents", headers=elektryk_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r_admin = client.get("/documents", headers=admin_headers)
    assert len(r_admin.json()) == 2


def test_create_document_elektryk_ograniczony_do_przypisanych_magazynow(client, elektryk_headers, mocked_storage):
    """elektryk_user ma magazyny_dostepne=['Zabrze'] (patrz conftest.py) - ta sama regula RBAC co /match."""
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        r = client.post("/documents", files=files, data={"magazyn": "Czekanów"}, headers=elektryk_headers)
    assert r.status_code == 403


def test_get_document_zwraca_pozycje_w_fizycznej_kolejnosci_formularza(
    client, admin_headers, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Regresja (2026-07-28, zgloszone przez Bartka): tabela weryfikacji na ekranie pokazywala
    pozycje w losowej kolejnosci (sortowanie relacji Document.items po UUID), rozjezdzajac sie z
    ukladem kartki - mimo ze finalny plik TXT (generate_output(), Etap 9) juz sortowal poprawnie.
    AI celowo zwraca pozycje w kolejnosci ODWROTNEJ do fizycznego ukladu formularza."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    # Na kartce "Wkręt ocynk 4,2x16" jest fizycznie DUZO PONIZEJ "Wtyczka odbiornikowa 32A" -
    # AI tutaj zwraca je w odwrotnej kolejnosci, zeby test cokolwiek realnie sprawdzal.
    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Wkręt ocynk 4,2x16", "ilosc_wydana": "10", "confidence": 95},'
        '{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "1", "confidence": 98}'
        "]}"
    )
    key = f"documents/order-test/{admin_user.id}.jpg"
    from app.modules.documents.storage import get_storage
    get_storage().upload(key, _fake_jpeg(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    with patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=ai_response)):
        run_ocr_task(str(document.id), db_session)

    r = client.get(f"/documents/{document.id}", headers=admin_headers)
    assert r.status_code == 200
    nazwy = [it["rozpoznana_nazwa"] for it in r.json()["items"]]
    assert nazwy == ["Wtyczka odbiornikowa 32A (niebieska) 1F", "Wkręt ocynk 4,2x16"]
