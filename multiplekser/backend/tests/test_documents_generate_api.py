"""Testy integracyjne Etapu 9: PATCH /documents/{id}/items/{item_id} (weryfikacja ilosci przed
generowaniem) oraz POST /documents/{id}/generate (eksport TXT/CP1250 do Optima)."""
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


def _setup_catalog(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)


# ---- PATCH /documents/{id}/items/{item_id} ----

def test_patch_item_ustawia_ilosc_finalna(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    r = client.patch(f"/documents/{doc_id}/items/{item_id}", json={"ilosc_finalna": 5}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["ilosc_finalna"] == 5.0


def test_patch_item_pole_nieobecne_zostaje_bez_zmian(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "3", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item = doc_repo.get_document(db_session, doc_id).items[0]
    assert item.ilosc_finalna == 3.0  # domyslne "razem" - patrz pick_qty_razem

    r = client.patch(f"/documents/{doc_id}/items/{item.id}", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ilosc_finalna"] == 3.0


def test_patch_item_recznie_poprawia_kod(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "cos niejasnego xyz", "ilosc_wydana": "1", "confidence": 40}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    r = client.patch(
        f"/documents/{doc_id}/items/{item_id}",
        json={"match_kod": "KORYTKO 32X15"}, headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_kod"] == "KORYTKO 32X15"
    assert body["match_jm"] == "M"
    # Reczna korekta = potwierdzone dopasowanie - badge w UI (MatchQualityChip) czyta wprost
    # to pole, wiec musi przelaczyc sie z "bad" (czerwone "Brak dopasowania") na "ok".
    assert body["match_quality"] == "ok"
    assert body["match_score"] == 1.0


def test_patch_item_usuniecie_kodu_ustawia_quality_bad(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    """Odwrotny kierunek: skasowanie recznej korekty (null) musi wrocic do stanu
    "brak dopasowania", nie zostawiac starego "ok" z poprzedniej korekty."""
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "cos niejasnego xyz", "ilosc_wydana": "1", "confidence": 40}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    client.patch(f"/documents/{doc_id}/items/{item_id}", json={"match_kod": "KORYTKO 32X15"}, headers=admin_headers)
    r = client.patch(f"/documents/{doc_id}/items/{item_id}", json={"match_kod": None}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_kod"] is None
    assert body["match_quality"] == "bad"
    assert body["match_score"] == 0.0


def test_patch_item_niepoprawny_kod_zwraca_400(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    r = client.patch(
        f"/documents/{doc_id}/items/{item_id}",
        json={"match_kod": "NIE MA TAKIEGO KODU"}, headers=admin_headers,
    )
    assert r.status_code == 400


def test_patch_item_cudzy_dokument_zwraca_403(client, db_session, admin_user, magazynier_headers, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    r = client.patch(f"/documents/{doc_id}/items/{item_id}", json={"ilosc_finalna": 5}, headers=magazynier_headers)
    assert r.status_code == 403


def test_patch_item_nieistniejacy_zwraca_404(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.patch(
        f"/documents/{doc_id}/items/00000000-0000-0000-0000-000000000000",
        json={"ilosc_finalna": 5}, headers=admin_headers,
    )
    assert r.status_code == 404


# ---- POST /documents/{id}/generate ----

def test_generate_wymaga_statusu_done(client, db_session, admin_user, admin_headers, mocked_storage):
    key = f"documents/test/{admin_user.id}-queued.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    r = client.post(f"/documents/{document.id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 409


def test_generate_zwraca_plik_cp1250_z_dyspozycja_pobrania(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = (
        '{"numer_projektu": "12/06/26", "pozycje": ['
        '{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "3", "confidence": 99}'
        "]}"
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response, magazyn="Czekanów")

    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "attachment" in r.headers["content-disposition"]
    assert "12-06-2026.txt" in r.headers["content-disposition"]
    assert r.headers["content-type"].startswith("text/plain")

    text = r.content.decode("cp1250")
    assert text == "WTYCZKA ODBIORNIKOWA 32A NIEBIESKA;3;;SZT;Czekanów"


def test_generate_pomija_pozycje_bez_ilosci_finalnej(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "confidence": 90}]}'  # brak ilosci -> ilosc_finalna None
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.content == b""


def test_generate_uzywa_ilosci_po_patch(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = (
        '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ma_oznaczenie": true, "confidence": 90}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    client.patch(f"/documents/{doc_id}/items/{item_id}", json={"ilosc_finalna": 2}, headers=admin_headers)
    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.content.decode("cp1250") == "GRZEJNIK 2000W;2;;SZT;"


def test_generate_uzywa_recznie_poprawionego_kodu(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    """Realny blad z produkcji (2026-07-31): generator ponownie dopasowywal SUROWA nazwe z OCR
    od zera, ignorujac reczna korekte match_kod zapisana przez PATCH - wygenerowany plik mial
    "BRAK DOPASOWANIA" mimo poprawnego kodu widocznego w UI. Nazwa ponizej ("cos niejasnego xyz")
    nigdy nie dopasuje sie sama - jedyny sposob zeby test przeszedl to uzycie zapisanej korekty."""
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "cos niejasnego xyz", "ilosc_wydana": "3", "confidence": 40}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)
    item_id = doc_repo.get_document(db_session, doc_id).items[0].id

    client.patch(f"/documents/{doc_id}/items/{item_id}", json={"match_kod": "KORYTKO 32X15"}, headers=admin_headers)
    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200
    assert r.content.decode("cp1250") == "KORYTKO 32X15;3;;M;"


def test_generate_qty_mode_ones(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = (
        '{"pozycje": [{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "9", "confidence": 99}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(f"/documents/{doc_id}/generate", json={"qty_mode": "ones"}, headers=admin_headers)
    assert r.status_code == 200
    assert r.content.decode("cp1250") == "WTYCZKA ODBIORNIKOWA 32A NIEBIESKA;1;;SZT;"


def test_generate_first_wydawka_dodaje_baze(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = (
        '{"pozycje": [{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", "ilosc_wydana": "1", "confidence": 99}]}'
    )
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(f"/documents/{doc_id}/generate", json={"first_wydawka": True}, headers=admin_headers)
    assert r.status_code == 200
    text = r.content.decode("cp1250")
    assert "SZYNA GRZEBIENIOWA WIDEŁKOWA;1;;SZT;" in text
    assert "KORYTKO 32X15;1;;M;" in text


def test_generate_cudzy_dokument_zwraca_403(client, db_session, admin_user, magazynier_headers, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 90}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=magazynier_headers)
    assert r.status_code == 403


def test_generate_hydraulika_dziala_wlasnym_generatorem(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """Krok Hydraulika-5: /generate uzywa generate_output_hydraulika() dla dokumentow tego
    dzialu (Krok 2/3 blokowaly to jawnym 409 - odblokowane po porcie generatora)."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    key = f"documents/test/{admin_user.id}-hydraulika.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    classify_response = '{"dzial":"hydraulika","confidence":95.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 97}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(str(document.id), db_session)

    r = client.post(f"/documents/{document.id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    text = r.content.decode("cp1250")
    assert text.strip() == "BOJLER 80 L;1;;SZT;"


def test_generate_hydraulika_zachowuje_kolejnosc_z_dokumentu_zrodlowego(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """Krok Hydraulika-5: bez fizycznego sortowania jak w Elektryce - kolejnosc wyniku musi
    odpowiadac kolejnosci pozycji zwroconej przez OCR (kolumna DocumentItemModel.sequence)."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    key = f"documents/test/{admin_user.id}-hydraulika-order.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    classify_response = '{"dzial":"hydraulika","confidence":95.0}'
    ocr_response = (
        '{"pozycje": ['
        '{"nazwa": "Zawór kątowy 1/2x3/4", "ilosc_wydana": "1", "confidence": 97},'
        '{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 97}'
        ']}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(str(document.id), db_session)

    r = client.post(f"/documents/{document.id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    kody = [line.split(";")[0] for line in r.content.decode("cp1250").strip().split("\n")]
    assert kody == ["ZAWÓR KĄTOWY 1/2X3/4", "BOJLER 80 L"]


def test_generate_hydraulika_uzywa_recznie_poprawionego_kodu(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """Ten sam realny blad co w Elektryce (patrz test_generate_uzywa_recznie_poprawionego_kodu),
    zweryfikowany tez dla wlasnego generatora Hydrauliki."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    key = f"documents/test/{admin_user.id}-hydraulika-recznie.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    classify_response = '{"dzial":"hydraulika","confidence":95.0}'
    ocr_response = '{"pozycje": [{"nazwa": "cos niejasnego xyz", "ilosc_wydana": "2", "confidence": 40}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(str(document.id), db_session)
    item_id = doc_repo.get_document(db_session, str(document.id)).items[0].id

    client.patch(f"/documents/{document.id}/items/{item_id}", json={"match_kod": "BOJLER 80 L"}, headers=admin_headers)
    r = client.post(f"/documents/{document.id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.content.decode("cp1250").strip() == "BOJLER 80 L;2;;SZT;"


# ---- POST /documents/{id}/items (dodanie pozycji recznie, spoza OCR) ----

def test_add_item_dodaje_nowa_pozycje(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(
        f"/documents/{doc_id}/items", json={"match_kod": "KORYTKO 32X15", "ilosc_finalna": 3},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["match_kod"] == "KORYTKO 32X15"
    assert body["match_jm"] == "M"
    assert body["match_quality"] == "ok"
    assert body["ilosc_finalna"] == 3.0
    assert body["ilosc_wydana"] is None

    document = doc_repo.get_document(db_session, doc_id)
    assert len(document.items) == 2


def test_add_item_niepoprawny_kod_zwraca_400(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(
        f"/documents/{doc_id}/items", json={"match_kod": "NIE MA TAKIEGO KODU", "ilosc_finalna": 1},
        headers=admin_headers,
    )
    assert r.status_code == 400


def test_add_item_wymaga_statusu_done(client, db_session, admin_user, admin_headers, mocked_storage):
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key="documents/test/queued.jpg", mime="image/jpeg",
        original_filename="skan.jpg",
    )
    r = client.post(
        f"/documents/{document.id}/items", json={"match_kod": "KORYTKO 32X15", "ilosc_finalna": 1},
        headers=admin_headers,
    )
    assert r.status_code == 409


def test_add_item_cudzy_dokument_zwraca_403(client, db_session, admin_user, magazynier_headers, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    r = client.post(
        f"/documents/{doc_id}/items", json={"match_kod": "KORYTKO 32X15", "ilosc_finalna": 1},
        headers=magazynier_headers,
    )
    assert r.status_code == 403


def test_add_item_trafia_do_wygenerowanego_pliku(client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_elektryka_json):
    """Reczne dodanie ma dzialac dokladnie jak reczna korekta istniejacej pozycji (patrz
    test_generate_uzywa_recznie_poprawionego_kodu) - trafia do wygenerowanego pliku, nie tylko
    do widoku weryfikacji."""
    _setup_catalog(db_session, baza_elektryka_json)
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    doc_id = _create_done_document(db_session, admin_user, ai_response)

    client.post(
        f"/documents/{doc_id}/items", json={"match_kod": "KORYTKO 32X15", "ilosc_finalna": 5},
        headers=admin_headers,
    )
    r = client.post(f"/documents/{doc_id}/generate", json={}, headers=admin_headers)
    assert r.status_code == 200, r.text
    text = r.content.decode("cp1250")
    assert "KORYTKO 32X15;5;;M;" in text
    assert "GRZEJNIK 2000W;1;;SZT;" in text


def test_add_item_hydraulika_dziala_na_katalogu_wlasciwego_dzialu(
    client, db_session, admin_user, admin_headers, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    key = f"documents/test/{admin_user.id}-hydraulika-add.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg", original_filename="skan.jpg",
    )
    classify_response = '{"dzial":"hydraulika","confidence":95.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 97}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(str(document.id), db_session)

    r = client.post(
        f"/documents/{document.id}/items", json={"match_kod": "ZAWÓR KĄTOWY 1/2X3/4", "ilosc_finalna": 2},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["match_kod"] == "ZAWÓR KĄTOWY 1/2X3/4"
