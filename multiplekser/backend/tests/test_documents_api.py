"""Testy integracyjne Etapu 7: POST/GET /documents. dispatch_ocr_task() jest zamockowane
(no-op) - logika przetwarzania jest juz w pelni pokryta w test_documents_task.py; tu testujemy
kontrakt API (upload do storage, zapis wiersza, RBAC wlasciciela/magazynu, statusy HTTP)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.router import _build_file_key
from app.modules.documents.tasks import run_ocr_task
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules


def _fake_jpeg() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="green").save(buf, format="JPEG")
    return buf.getvalue()


def _no_delay():
    return patch("app.modules.documents.router.dispatch_ocr_task")


def test_klucze_dwoch_stron_o_tej_samej_nazwie_sa_unikalne():
    import uuid

    document_id = uuid.uuid4()
    first_key = _build_file_key(document_id, 1, "skan.jpg")
    second_key = _build_file_key(document_id, 2, "skan.jpg")
    assert first_key != second_key
    assert "/001-" in first_key
    assert "/002-" in second_key
    assert first_key.endswith("-skan.jpg")
    assert second_key.endswith("-skan.jpg")


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
    with _no_delay() as mock_dispatch:
        r = client.post("/documents", files=files, headers=admin_headers)

    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["id"]
    mock_dispatch.assert_called_once_with(body["id"])


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


def test_get_document_cudzy_zwraca_403_dla_nie_admina(client, admin_headers, magazynier_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=admin_headers).json()

    r = client.get(f"/documents/{created['id']}", headers=magazynier_headers)
    assert r.status_code == 403


def test_get_document_admin_widzi_cudzy_dokument(client, admin_headers, magazynier_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        created = client.post("/documents", files=files, headers=magazynier_headers).json()

    r = client.get(f"/documents/{created['id']}", headers=admin_headers)
    assert r.status_code == 200


def test_list_documents_nieadmin_widzi_tylko_swoje(client, admin_headers, magazynier_headers, mocked_storage):
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        client.post("/documents", files=files, headers=admin_headers)
        client.post("/documents", files=files, headers=magazynier_headers)

    r = client.get("/documents", headers=magazynier_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    r_admin = client.get("/documents", headers=admin_headers)
    assert len(r_admin.json()) == 2


def test_create_document_dwa_pliki_tworzy_jeden_dokument_z_dodatkowa_strona(client, admin_headers, db_session, mocked_storage):
    """Realna potrzeba (patrz historia czatu): papierowa wydawka na dwoch zdjeciach z telefonu -
    oba pliki musza trafic do JEDNEGO dokumentu (druga strona jako DocumentFileModel), nie do
    dwoch osobnych dokumentow."""
    files = [
        ("plik", ("strona1.jpg", _fake_jpeg(), "image/jpeg")),
        ("plik", ("strona2.jpg", _fake_jpeg(), "image/jpeg")),
    ]
    with _no_delay():
        r = client.post("/documents", files=files, headers=admin_headers)
    assert r.status_code == 202, r.text
    body = r.json()

    document = doc_repo.get_document(db_session, body["id"])
    assert document.original_filename == "strona1.jpg"
    assert len(document.extra_files) == 1
    assert document.extra_files[0].mime == "image/jpeg"


def test_create_document_dwa_pliki_o_tej_samej_nazwie_maja_rozne_klucze(
    client, admin_headers, db_session, mocked_storage,
):
    """Dwie strony z telefonu/skanera moga miec identyczna nazwe i nie moga sie nadpisac."""
    first_page = _fake_jpeg()
    second_page = first_page + b"-druga-strona"
    files = [
        ("plik", ("skan.jpg", first_page, "image/jpeg")),
        ("plik", ("skan.jpg", second_page, "image/jpeg")),
    ]
    with _no_delay():
        r = client.post("/documents", files=files, headers=admin_headers)
    assert r.status_code == 202, r.text

    document = doc_repo.get_document(db_session, r.json()["id"])
    keys = [document.file_key, document.extra_files[0].file_key]
    assert keys[0] != keys[1]
    assert "/001-" in keys[0]
    assert "/002-" in keys[1]

    from app.modules.documents.storage import get_storage
    storage = get_storage()
    assert storage.download(keys[0]) == first_page
    assert storage.download(keys[1]) == second_page


def test_create_document_magazynier_ma_dostep_do_kazdego_magazynu(client, magazynier_headers, mocked_storage):
    """magazynier_user ma magazyny_dostepne=['Zabrze'] (patrz conftest.py), ale ograniczenie
    RBAC do przypisanych magazynow zostalo usuniete (2026-08-04, na zyczenie uzytkownika) -
    magazynier ma teraz pelny dostep do kazdego magazynu, tak jak admin."""
    files = {"plik": ("skan.jpg", _fake_jpeg(), "image/jpeg")}
    with _no_delay():
        r = client.post("/documents", files=files, data={"magazyn": "Czekanów"}, headers=magazynier_headers)
    assert r.status_code == 202, r.text


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
