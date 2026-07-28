"""Testy Etapu 7: run_ocr_task() - logika przetwarzania w tle, testowana bez brokera/workera
(sesja przekazana wprost, jak w reszcie testow integracyjnych - patrz docstring tasks.py)."""
from io import BytesIO
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import process_ocr_document, run_ocr_task
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
