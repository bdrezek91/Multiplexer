"""Testy integracyjne Etapu 7: POST/GET /documents. process_ocr_document.delay() jest zamockowane
(no-op) - logika przetwarzania jest juz w pelni pokryta w test_documents_task.py; tu testujemy
kontrakt API (upload do storage, zapis wiersza, RBAC wlasciciela/magazynu, statusy HTTP)."""
from io import BytesIO
from unittest.mock import patch

from PIL import Image


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
