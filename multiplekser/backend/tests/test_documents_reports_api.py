"""Testy integracyjne funkcji "Zglos problem" (2026-09-08, na zyczenie uzytkownika) -
POST /documents/{id}/reports (kazdy zalogowany z dostepem do dokumentu), GET
/documents/reports/list i PATCH /documents/reports/{id}/resolve (tylko admin)."""
from io import BytesIO
from unittest.mock import patch

from PIL import Image


def _fake_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="green").save(buf, format="JPEG")
    return buf.getvalue()


def _no_delay():
    return patch("app.modules.documents.router.dispatch_ocr_task")


def _create_document(client, headers, mocked_storage) -> str:
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        r = client.post("/documents", files=files, headers=headers)
    return r.json()["id"]


def test_create_report_przez_wlasciciela_zwraca_201(client, admin_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)

    r = client.post(
        f"/documents/{document_id}/reports", json={"opis": "Zle rozpoznana ilosc w wierszu 3"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["document_id"] == document_id
    assert body["opis"] == "Zle rozpoznana ilosc w wierszu 3"
    assert body["status"] == "open"
    assert body["resolved_at"] is None


def test_create_report_bez_dostepu_do_dokumentu_zwraca_403(
    client, admin_headers, magazynier_headers, mocked_storage,
):
    document_id = _create_document(client, admin_headers, mocked_storage)

    r = client.post(
        f"/documents/{document_id}/reports", json={"opis": "Cos jest zle"},
        headers=magazynier_headers,
    )
    assert r.status_code == 403


def test_create_report_nieznany_dokument_zwraca_404(client, admin_headers):
    r = client.post(
        "/documents/00000000-0000-0000-0000-000000000000/reports",
        json={"opis": "Cos jest zle"}, headers=admin_headers,
    )
    assert r.status_code == 404


def test_create_report_pusty_opis_zwraca_422(client, admin_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)

    r = client.post(f"/documents/{document_id}/reports", json={"opis": ""}, headers=admin_headers)
    assert r.status_code == 422


def test_list_reports_przez_zwyklego_uzytkownika_zwraca_403(client, magazynier_headers):
    r = client.get("/documents/reports/list", headers=magazynier_headers)
    assert r.status_code == 403


def test_list_reports_przez_admina_widzi_zgloszenie(client, admin_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)
    client.post(f"/documents/{document_id}/reports", json={"opis": "Blad OCR"}, headers=admin_headers)

    r = client.get("/documents/reports/list", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["opis"] == "Blad OCR"
    assert body[0]["document_original_filename"] == "skan.jpg"
    assert body[0]["reported_by_email"]


def test_list_reports_filtruje_po_statusie(client, admin_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)
    created = client.post(
        f"/documents/{document_id}/reports", json={"opis": "Blad OCR"}, headers=admin_headers,
    ).json()

    client.patch(f"/documents/reports/{created['id']}/resolve", headers=admin_headers)

    open_reports = client.get("/documents/reports/list?status=open", headers=admin_headers).json()
    resolved_reports = client.get("/documents/reports/list?status=resolved", headers=admin_headers).json()
    assert open_reports == []
    assert len(resolved_reports) == 1
    assert resolved_reports[0]["status"] == "resolved"
    assert resolved_reports[0]["resolved_at"] is not None


def test_resolve_report_przez_zwyklego_uzytkownika_zwraca_403(
    client, admin_headers, magazynier_headers, mocked_storage,
):
    document_id = _create_document(client, admin_headers, mocked_storage)
    created = client.post(
        f"/documents/{document_id}/reports", json={"opis": "Blad OCR"}, headers=admin_headers,
    ).json()

    r = client.patch(f"/documents/reports/{created['id']}/resolve", headers=magazynier_headers)
    assert r.status_code == 403


def test_resolve_report_nieznane_zgloszenie_zwraca_404(client, admin_headers):
    r = client.patch(
        "/documents/reports/00000000-0000-0000-0000-000000000000/resolve", headers=admin_headers,
    )
    assert r.status_code == 404


def test_get_document_file_zwraca_oryginalny_skan(client, admin_headers, mocked_storage):
    raw = _fake_jpeg()
    files = {"plik": ("skan.jpg", raw, "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=admin_headers).json()

    r = client.get(f"/documents/{created['id']}/file", headers=admin_headers)
    assert r.status_code == 200
    assert r.content == raw
    assert r.headers["content-type"] == "image/jpeg"
    assert "inline" in r.headers["content-disposition"]


def test_get_document_file_bez_dostepu_zwraca_403(client, admin_headers, magazynier_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)

    r = client.get(f"/documents/{document_id}/file", headers=magazynier_headers)
    assert r.status_code == 403


def test_get_document_file_nieznana_strona_zwraca_404(client, admin_headers, mocked_storage):
    document_id = _create_document(client, admin_headers, mocked_storage)

    r = client.get(f"/documents/{document_id}/file?page=2", headers=admin_headers)
    assert r.status_code == 404
