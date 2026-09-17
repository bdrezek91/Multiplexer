"""Testy integracyjne linku Optima (2026-09-17) - staly, anonimowy URL do receptury TXT dla
Comarch ERP Optima (nie potrafi zalogowac sie ani wyslac Bearer tokena, pobiera plik zwyklym
GET). POST/DELETE /{document_id}/optima-link wymagaja zalogowania (owner/admin) - GET
/optima/recipe/{document_id}/{token}.txt jest anonimowy, zabezpieczony wylacznie tokenem."""
import re
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import run_ocr_task
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules

_URL_RE = re.compile(r"^http://localhost:8000/api/optima/recipe/([0-9a-f-]{36})/([\w-]{20,})\.txt$")


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


def _setup_catalog(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)


_AI_RESPONSE = (
    '{"pozycje": [{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "1", "confidence": 99}]}'
)


def _extract_token(url: str) -> str:
    m = _URL_RE.match(url)
    assert m, f"URL nie pasuje do oczekiwanego wzorca: {url}"
    return m.group(2)


# ---- POST /{document_id}/optima-link ----

def test_create_optima_link_zwraca_url_pasujacy_do_wzorca(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE, magazyn="Czekanów")

    r = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers)
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert _URL_RE.match(url)
    assert f"/optima/recipe/{doc_id}/" in url


def test_create_optima_link_bez_tokenu_zwraca_401(client, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    r = client.post(f"/documents/{doc_id}/optima-link")
    assert r.status_code == 401


def test_create_optima_link_cudzy_dokument_zwraca_403(
    client, db_session, admin_user, magazynier_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    r = client.post(f"/documents/{doc_id}/optima-link", headers=magazynier_headers)
    assert r.status_code == 403


def test_create_nowy_token_uniewaznia_stary(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    first_url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]
    r_first_before = client.get(_path_from_url(first_url))
    assert r_first_before.status_code == 200

    second_url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]
    assert second_url != first_url

    r_first_after = client.get(_path_from_url(first_url))
    assert r_first_after.status_code == 404

    r_second = client.get(_path_from_url(second_url))
    assert r_second.status_code == 200


def _path_from_url(url: str) -> str:
    return url.split("localhost:8000", 1)[1].replace("/api/", "/", 1)


# ---- DELETE /{document_id}/optima-link ----

def test_delete_optima_link_uniewaznia_token(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    r_delete = client.delete(f"/documents/{doc_id}/optima-link", headers=admin_headers)
    assert r_delete.status_code == 204

    r_get = client.get(_path_from_url(url))
    assert r_get.status_code == 404


def test_delete_optima_link_bez_tokenu_zwraca_401(client, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    r = client.delete(f"/documents/{doc_id}/optima-link")
    assert r.status_code == 401


def test_delete_optima_link_cudzy_dokument_zwraca_403(
    client, db_session, admin_user, admin_headers, magazynier_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)
    client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers)

    r = client.delete(f"/documents/{doc_id}/optima-link", headers=magazynier_headers)
    assert r.status_code == 403


# ---- GET /optima/recipe/{document_id}/{token}.txt ----

def test_get_recipe_poprawny_token_zwraca_dokladny_txt(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE, magazyn="Czekanów")
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    r = client.get(_path_from_url(url))
    assert r.status_code == 200, r.text
    assert r.content.decode("cp1250") == "WTYCZKA ODBIORNIKOWA 32A NIEBIESKA;1;;SZT;Czekanów"


def test_get_recipe_dziala_bez_authorization(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Kluczowe dla Optimy - anonimowy klient nigdy nie wysyla naglowka Authorization."""
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    # `client` fixture nie dolacza domyslnie Authorization - to jest juz "anonimowe" wywolanie,
    # ale sprawdzamy to jawnie, zeby test nie polegal cicho na tym zalozeniu.
    r = client.get(_path_from_url(url), headers={})
    assert r.status_code == 200
    assert "authorization" not in {h.lower() for h in r.request.headers.keys()}


def test_get_recipe_content_type_i_naglowki(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    r = client.get(_path_from_url(url))
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/plain; charset=windows-1250"
    assert "inline" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


def test_get_recipe_kazda_linia_ma_format_kod_ilosc_pusty_jm_magazyn(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "1", "confidence": 99},'
        '{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "2", "confidence": 99}'
        "]}"
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response, magazyn="Zabrze")
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    r = client.get(_path_from_url(url))
    text = r.content.decode("cp1250")
    lines = [l for l in text.split("\n") if l]
    assert len(lines) == 2
    for line in lines:
        parts = line.split(";")
        assert len(parts) == 5
        assert parts[2] == ""  # trzecie pole zawsze puste
        kod, ilosc, _, jm, magazyn = parts
        assert kod != ""
        float(ilosc)  # nie rzuca
        assert jm != ""
        assert magazyn == "Zabrze"


def test_get_recipe_brak_tokena_zwraca_404(client, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    r = client.get(f"/optima/recipe/{doc_id}/nieprawidlowy-token-losowy-1234567890.txt")
    assert r.status_code == 404


def test_get_recipe_dokument_bez_aktywnego_linku_zwraca_404(
    client, db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_id = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    r = client.get(f"/optima/recipe/{doc_id}/dowolny-token-nigdy-nie-utworzony-xx.txt")
    assert r.status_code == 404


def test_get_recipe_token_jednego_dokumentu_nie_dziala_dla_innego(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    doc_a = _create_done_document(db_session, admin_user, _AI_RESPONSE)
    doc_b = _create_done_document(db_session, admin_user, _AI_RESPONSE)

    url_a = client.post(f"/documents/{doc_a}/optima-link", headers=admin_headers).json()["url"]
    token_a = _extract_token(url_a)

    r_cross = client.get(f"/optima/recipe/{doc_b}/{token_a}.txt")
    assert r_cross.status_code == 404

    r_own = client.get(_path_from_url(url_a))
    assert r_own.status_code == 200


def test_get_recipe_dokument_nie_gotowy_zwraca_409(client, db_session, admin_user, admin_headers, mocked_storage):
    key = f"documents/test/{admin_user.id}-queued.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    # Link mozna utworzyc niezaleznie od statusu dokumentu - odczyt dopiero pilnuje "done".
    token = doc_repo.create_optima_share_link(db_session, document)

    r = client.get(f"/optima/recipe/{document.id}/{token}.txt")
    assert r.status_code == 409


def test_get_recipe_dokument_bez_pozycji_zwraca_409(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "confidence": 90}]}'  # brak ilosci -> ilosc_finalna None
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    url = client.post(f"/documents/{doc_id}/optima-link", headers=admin_headers).json()["url"]

    r = client.get(_path_from_url(url))
    assert r.status_code == 409
