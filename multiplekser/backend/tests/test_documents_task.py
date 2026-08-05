"""Testy Etapu 7: run_ocr_task() - logika przetwarzania w tle, testowana bez brokera/workera
(sesja przekazana wprost, jak w reszcie testow integracyjnych - patrz docstring tasks.py)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import process_ocr_document, run_ocr_task
from app.modules.ocr.providers import OCRProviderError
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES


def _fake_jpeg_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (50, 50), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


def _mock_recognize(response_text: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=response_text))


def _create_document(db_session, admin_user, magazyn=None) -> str:
    key = f"documents/test/{admin_user.id}.jpg"
    get_storage().upload(key, _fake_jpeg_bytes(), "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg",
        original_filename="skan.jpg", magazyn=magazyn,
    )
    return str(document.id)


def test_run_ocr_task_dokument_nieistniejacy_nic_nie_robi(db_session):
    run_ocr_task("00000000-0000-0000-0000-000000000000", db_session)  # nie rzuca wyjatku


def test_run_ocr_task_dwa_pliki_wysyla_oba_w_jednym_zapytaniu(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Realna potrzeba (patrz historia czatu): papierowa wydawka nie zmiescila sie na jednym
    zdjeciu z telefonu, wiec pracownik robi dwa osobne zdjecia (dwie strony jednego dokumentu).
    Oba musza trafic do Gemini w JEDNYM zapytaniu (patrz prompt.py, WIELE OBRAZOW), zeby model
    polaczyl pozycje z obu stron w jedna liste - nie dwa osobne wywolania/dwa osobne wyniki."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    strona1 = _fake_jpeg_bytes()
    strona2 = _fake_jpeg_bytes()
    key1 = f"documents/test/{admin_user.id}-strona1.jpg"
    key2 = f"documents/test/{admin_user.id}-strona2.jpg"
    get_storage().upload(key1, strona1, "image/jpeg")
    get_storage().upload(key2, strona2, "image/jpeg")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key1, mime="image/jpeg",
        original_filename="strona1.jpg", extra_files=[(key2, "image/jpeg")],
    )

    ai_response = (
        '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=ai_response),
    ) as mock_recognize:
        run_ocr_task(str(document.id), db_session)

    # KAZDE wywolanie recognize() (klasyfikacja + pelny odczyt) musi dostac OBIE strony naraz.
    assert mock_recognize.call_count == 2  # klasyfikacja + pelny odczyt
    for call in mock_recognize.call_args_list:
        files = call.kwargs["files"]
        assert len(files) == 2
        assert files[0][1] == "image/jpeg"
        assert files[1][1] == "image/jpeg"

    saved = doc_repo.get_document(db_session, str(document.id))
    assert saved.status == "done"
    assert len(saved.extra_files) == 1
    assert saved.extra_files[0].file_key == key2


def test_run_ocr_task_sukces_zapisuje_pozycje(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"numer_projektu": "35/06/26", "pozycje": ['
        '{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "ilosc_zuzyta": "1", "confidence": 98.5}'
        "]}"
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.numer_projektu == "35/06/2026"
    assert document.used_provider == "Gemini 3.6 Flash (klucz darmowy)"
    assert document.rejected_count == 0
    assert len(document.items) == 1

    item = document.items[0]
    assert item.rozpoznana_nazwa == "Grzejnik 1800W"
    assert item.ilosc_wydana == 1.0
    assert item.match_kod == "GRZEJNIK 2000W"
    assert item.match_quality == "ok"
    assert item.matched_product_id is not None
    assert item.off_form is True


def test_run_ocr_task_uzywa_openai_jako_ostatniego_fallbacku_lancucha(
    db_session, admin_user, mocked_storage, gemini_key_configured, openai_key_configured, baza_elektryka_json,
):
    """OpenAI jest ostatnim ogniwem default_ocr_chain() (patrz ocr/chain.py) - uzywany WYLACZNIE
    gdy wszystkie kroki Gemini (darmowy x4 + platny) zawioda, nigdy rownolegle do Gemini."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    openai_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    with (
        patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(side_effect=OCRProviderError("timeout"))),
        patch("app.modules.ocr.providers.OpenAIProvider.recognize", new=AsyncMock(return_value=openai_response)),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert "OpenAI" in document.used_provider
    assert document.items[0].ilosc_wydana == 1.0


def test_run_ocr_task_odrzuca_niepoprawne_pozycje(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = '{"pozycje": [{"nazwa": "X"}, {"nazwa": "Peszel", "ilosc_wydana": "3"}]}'
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.rejected_count == 1
    assert len(document.items) == 1
    assert document.items[0].match_kod == "RURA KARBOWANA FI16"


def test_run_ocr_task_uzywa_magazynu_dokumentu(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user, magazyn="Czekanów")

    ai_response = '{"pozycje": [{"nazwa": "Bezpiecznik 25A Niemiecki", "ilosc_wydana": "1"}]}'
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.items[0].match_kod == "BEZPIECZNIK 25A NIEMIECKI 1P"


def test_run_ocr_task_nie_json_ustawia_status_error(db_session, admin_user, mocked_storage, gemini_key_configured):
    document_id = _create_document(db_session, admin_user)
    with _mock_recognize("Przepraszam, nie moge pomoc z tym zadaniem."):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "error"
    assert "nie-JSON" in document.error_message
    assert document.items == []


def test_run_ocr_task_brak_klucza_api_ustawia_status_error(db_session, admin_user, mocked_storage):
    from app.core.config import settings

    original_free, original_paid = settings.gemini_api_key_free, settings.gemini_api_key_paid
    settings.gemini_api_key_free, settings.gemini_api_key_paid = None, None
    try:
        document_id = _create_document(db_session, admin_user)
        run_ocr_task(document_id, db_session)
    finally:
        settings.gemini_api_key_free, settings.gemini_api_key_paid = original_free, original_paid

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "error"
    assert "klucza" in document.error_message


# ---- Krok Hydraulika-3: klasyfikacja automatyczna dzialu (dwa kolejne wywolania recognize) ----

def _mock_recognize_sequence(*responses: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(side_effect=list(responses)))


def test_run_ocr_task_klasyfikuje_hydraulike_i_uzywa_jej_katalogu(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":91.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Zawór kątowy 1/2x3/4", "ilosc_wydana": "2", "confidence": 97}]}'
    with _mock_recognize_sequence(classify_response, ocr_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.dzial == "hydraulika"
    assert document.dzial_confidence == 91.0
    assert len(document.items) == 1
    assert document.items[0].match_kod == "ZAWÓR KĄTOWY 1/2X3/4"


def test_run_ocr_task_klasyfikacja_niesparsowalna_pozostaje_na_elektryce(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Fallback klasyfikacji (elektryka, confidence 0) nie moze zmienic dotychczasowego
    zachowania - dokument bez wykrytego dzialu nadal jest przetwarzany jako Elektryka."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    classify_response = "nie rozumiem"
    ocr_response = '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    with _mock_recognize_sequence(classify_response, ocr_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.dzial == "elektryka"
    assert document.dzial_confidence == 0.0
    assert document.items[0].match_kod == "GRZEJNIK 2000W"


def test_process_ocr_document_deleguje_do_run_ocr_task():
    """Wiring Celery: process_ocr_document to CIENKI wrapper - test bez brokera/DB, weryfikuje
    tylko, ze otwiera sesje i przekazuje jej referencje dalej do run_ocr_task."""
    from unittest.mock import MagicMock

    fake_session = MagicMock()
    with patch("app.modules.documents.tasks.SessionLocal", return_value=fake_session) as session_factory, \
         patch("app.modules.documents.tasks.run_ocr_task") as run_task:
        process_ocr_document.run("some-document-id")

    session_factory.assert_called_once()
    run_task.assert_called_once_with("some-document-id", fake_session)
    fake_session.close.assert_called_once()


# ---- Retry na przejsciowe bledy sieci/dostepnosci (patrz docs/RAPORT_OCR_NIEZAWODNOSC_1.md) ----

def test_run_ocr_task_ponawia_po_przejsciowym_bledzie_i_konczy_sukcesem(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """Pierwsza proba pada calkowicie (kazdy krok lancucha z kluczem darmowym zwraca blad
    dostepnosci - AllProvidersFailedError), druga (po odczekaniu) juz sie udaje - dokument
    konczy sie na status="done", nie "error"."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":93.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 97}]}'
    # Tylko cztery kroki Gemini na kluczu darmowym maja klucz skonfigurowany
    # (gemini_key_configured) - kroki platne (Gemini/OpenAI) sa pomijane (brak klucza), wiec
    # wszystkie 4 darmowe kroki musza zawiesc w pierwszej probie klasyfikacji. Dopiero druga
    # proba (attempt 1) dochodzi do sukcesu.
    responses = [OCRProviderError("timeout")] * 4 + [classify_response, ocr_response]
    with patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(side_effect=responses)), \
         patch("app.modules.documents.tasks.time.sleep") as fake_sleep:
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.dzial == "hydraulika"
    fake_sleep.assert_called_once_with(5)  # jedno opoznienie miedzy 1. a 2. proba


def test_run_ocr_task_wyczerpuje_proby_i_konczy_sie_bledem(
    db_session, admin_user, mocked_storage, gemini_key_configured,
):
    """Kazda z 3 prob pada tym samym bledem dostepnosci - dokument konczy sie na status="error"
    (dokladnie tak jak przed wprowadzeniem retry), nie wisi w nieskonczonosc."""
    document_id = _create_document(db_session, admin_user)

    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=OCRProviderError("timeout")),
    ), patch("app.modules.documents.tasks.time.sleep") as fake_sleep:
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "error"
    assert fake_sleep.call_count == 2  # 2 opoznienia miedzy 3 probami (5s, 15s)


# ---- Druga, waska proba dla pozycji z pusta iloscia w obu kolumnach (patrz ocr/verify.py) ----

def test_run_ocr_task_druga_proba_uzupelnia_pomijeta_ilosc(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":93.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "confidence": 90}]}'  # brak ilosci
    verify_response = '{"ilosc_wydana": 1, "ilosc_zuzyta": null}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response, verify_response]),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].ilosc_wydana == 1.0
    assert document.items[0].ilosc_finalna == 1.0


def test_run_ocr_task_druga_proba_bez_wyniku_zostawia_ilosc_pusta(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":93.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "confidence": 90}]}'
    verify_response = '{"ilosc_wydana": null, "ilosc_zuzyta": null}'  # sam ptaszek, bez cyfry
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response, verify_response]),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].ilosc_wydana is None
    assert document.items[0].ilosc_finalna is None
