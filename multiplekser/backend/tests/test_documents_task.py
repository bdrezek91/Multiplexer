"""Testy Etapu 7: run_ocr_task() - logika przetwarzania w tle, testowana bez brokera/workera
(sesja przekazana wprost, jak w reszcie testow integracyjnych - patrz docstring tasks.py)."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from app.modules.documents import repository as doc_repo
from app.modules.documents.storage import get_storage
from app.modules.documents.tasks import (
    _append_auto_zasilacz_led,
    _background_review_item,
    process_ocr_document,
    run_full_document_verification_task,
    run_ocr_task,
)
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

    classify_response = '{"dzial":"elektryka","confidence":98.0}'
    ocr_response = (
        '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ) as mock_recognize:
        run_ocr_task(str(document.id), db_session)

    # Klasyfikacja dostaje tylko miniaturke naglowka pierwszej strony; glowny OCR nadal OBIE
    # strony naraz. Druga pelna kontrola jest osobnym taskiem i nie blokuje run_ocr_task().
    assert mock_recognize.call_count == 2
    classify_files = mock_recognize.call_args_list[0].kwargs["files"]
    assert len(classify_files) == 1
    assert classify_files[0][1] == "image/jpeg"

    ocr_files = mock_recognize.call_args_list[1].kwargs["files"]
    assert len(ocr_files) == 2
    assert ocr_files[0][1] == "image/jpeg"
    assert ocr_files[1][1] == "image/jpeg"

    saved = doc_repo.get_document(db_session, str(document.id))
    assert saved.status == "done"
    assert len(saved.extra_files) == 1
    assert saved.extra_files[0].file_key == key2


def _fake_two_page_pdf_bytes() -> bytes:
    """PDF ze skanera z dwiema stronami - realny przypadek (patrz historia czatu 2026-09-09:
    dwustronicowy PDF, model zgubil gorna czesc pierwszej strony przy natywnym odczycie calego
    pliku PDF)."""
    import fitz

    doc = fitz.open()
    for text in ("strona 1", "strona 2"):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    buf = BytesIO(doc.tobytes())
    doc.close()
    return buf.getvalue()


def test_run_ocr_task_pdf_wielostronicowy_rozbity_na_osobne_obrazy(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Wielostronicowy PDF NIE jest wysylany natywnie jako jeden plik - kazda strona trafia jako
    OSOBNY obraz (patrz ocr/image.py: pdf_to_page_images i tasks.py: _download_and_prepare) -
    ten sam, juz sprawdzony mechanizm co "kilka zdjec z telefonu" powyzej. Natywny PDF byl mniej
    niezawodny na gestych, wielostronicowych dokumentach (model gubil fragmenty tresci)."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    key = f"documents/test/{admin_user.id}-skan.pdf"
    get_storage().upload(key, _fake_two_page_pdf_bytes(), "application/pdf")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="application/pdf",
        original_filename="skan.pdf",
    )

    classify_response = '{"dzial":"elektryka","confidence":98.0}'
    ocr_response = (
        '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ) as mock_recognize:
        run_ocr_task(str(document.id), db_session)

    assert mock_recognize.call_count == 2
    classify_files = mock_recognize.call_args_list[0].kwargs["files"]
    assert len(classify_files) == 1
    assert classify_files[0][1] == "image/jpeg"

    ocr_files = mock_recognize.call_args_list[1].kwargs["files"]
    assert len(ocr_files) == 2  # dwie strony PDF = dwie osobne czesci glownego zapytania
    for _file_bytes, mime in ocr_files:
        assert mime == "image/jpeg"  # rozbite na obrazy, nie natywny "application/pdf"

    saved = doc_repo.get_document(db_session, str(document.id))
    assert saved.status == "done"


def _fake_three_page_pdf_with_blank_middle() -> bytes:
    """Realny przypadek produkcyjny (2026-09-17): PDF ze skanera mial "widmowa", niemal calkiem
    biala strone 2 (przebicie druku z drugiej strony kartki na cienkim papierze) miedzy dwiema
    prawdziwymi stronami tresci - patrz ocr/image.py: is_blank_page. Strony "z tresc" maja
    narysowana siatke formularza (nie sam tekst - zbyt maly ciezar atramentu, zeby przekroczyc
    celowo bardzo niski prog is_blank_page), analogicznie do _synthetic_form_jpeg w
    test_ocr_image_deskew.py."""
    import fitz

    doc = fitz.open()
    for has_content in (True, False, True):
        page = doc.new_page()
        if has_content:
            for y in range(100, 700, 30):
                page.draw_line((50, y), (500, y), color=(0, 0, 0), width=1.5)
            page.draw_rect(fitz.Rect(50, 100, 500, 700), color=(0, 0, 0), width=1.5)
    buf = BytesIO(doc.tobytes())
    doc.close()
    return buf.getvalue()


def test_run_ocr_task_pomija_prawie_puste_strony_pdf(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    key = f"documents/test/{admin_user.id}-skan-pusta-strona.pdf"
    get_storage().upload(key, _fake_three_page_pdf_with_blank_middle(), "application/pdf")
    document = doc_repo.create_document(
        db_session, user_id=admin_user.id, file_key=key, mime="application/pdf",
        original_filename="skan.pdf",
    )

    classify_response = '{"dzial":"elektryka","confidence":98.0}'
    ocr_response = (
        '{"pozycje": [{"nazwa": "Grzejnik 1800W", "ilosc_wydana": "1", "confidence": 98}]}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ) as mock_recognize:
        run_ocr_task(str(document.id), db_session)

    assert mock_recognize.call_count == 2
    # Klasyfikacja od v1.0.24 dostaje tylko miniaturke naglowka pierwszej strony.
    classify_files = mock_recognize.call_args_list[0].kwargs["files"]
    assert len(classify_files) == 1

    # Glowny OCR nadal dostaje wszystkie niepuste strony: z 3 stron PDF srodkowa jest pusta,
    # wiec do OCR trafiaja 2 pelne strony.
    ocr_files = mock_recognize.call_args_list[1].kwargs["files"]
    assert len(ocr_files) == 2

    saved = doc_repo.get_document(db_session, str(document.id))
    assert saved.status == "done"


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
    assert document.used_provider == "Gemini 3 Flash Preview (klucz darmowy)"
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
    # Nieparsowalna odpowiedz jest odrzucana przez kazdy z czterech darmowych modeli,
    # a dopiero wyczerpanie lancucha uruchamia zgodny wstecznie fallback do Elektryki.
    with _mock_recognize_sequence(*([classify_response] * 4), ocr_response):
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
    # proba (attempt 1) dochodzi do sukcesu. Kolejne wywolanie to pelna kontrola spojnosci
    # dokumentu (_check_full_document_consistency) - potwierdza ten sam wynik co glowny odczyt.
    responses = [OCRProviderError("timeout")] * 4 + [classify_response, ocr_response, ocr_response]
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
    ocr_response = (
        '{"pozycje": [{"nazwa": "Bojler 80 L", "ma_oznaczenie": true, "confidence": 90}]}'
    )  # brak ilosci, ale widoczne oznaczenie kieruje pozycje do dodatkowej kontroli
    verify_response = '{"pozycje":[{"id":"1","ilosc_wydana":1,"ilosc_zuzyta":null}]}'
    # Czwarty odczyt to pelna kontrola spojnosci dokumentu (_check_full_document_consistency) -
    # potwierdza ten sam wynik co po dodatkowej kontroli ilosci.
    confirm_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1", "confidence": 90}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response, verify_response, confirm_response]),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].ilosc_wydana == 1.0
    assert document.items[0].ilosc_finalna == 1.0
    # Sygnal dla UI (walidacja architektury 2026-08-31) - ta ilosc pochodzi z dodatkowej
    # kontroli, nie z glownego modelu, wiec operator powinien ja zweryfikowac dokladniej.
    assert document.items[0].ilosc_z_dodatkowej_kontroli is True


def test_run_ocr_task_ilosc_z_glownego_modelu_nie_ma_flagi_dodatkowej_kontroli(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """Kontrastowy przypadek: pozycja odczytana pewnie za pierwszym razem (bez eskalacji do
    verify_ambiguous_quantities) nie powinna nigdy dostac flagi 'z dodatkowej kontroli'."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":93.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": 1, "confidence": 99}]}'
    # Trzeci odczyt to pelna kontrola spojnosci dokumentu (_check_full_document_consistency) -
    # potwierdza ten sam wynik co glowny odczyt, wiec NIE ustawia flagi dodatkowej kontroli
    # (tylko rozbieznosc by ja ustawila).
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response, ocr_response]),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].ilosc_wydana == 1.0
    assert document.items[0].ilosc_z_dodatkowej_kontroli is False


def test_run_ocr_task_tasma_led_dodaje_widoczny_zasilacz(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Na zyczenie uzytkownika (2026-08-31): zasilacz ma byc widoczny od razu na stronie
    weryfikacji jako normalna, zapisana pozycja - nie tylko doliczany przy generowaniu TXT."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Taśma LED 5M", "ilosc_wydana": "3", "confidence": 98},'
        '{"nazwa": "Taśma LED zielona", "ilosc_wydana": "2", "confidence": 98}'
        ']}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    # 2 pozycje tasmy z kartki + 1 automatycznie dodany zasilacz (2 wystapienia = 2 szt.).
    assert len(document.items) == 3
    zasilacz = next(it for it in document.items if it.match_kod == "ZASILACZ LED 75W")
    assert zasilacz.rozpoznana_nazwa == "Zasilacz LED 75W"
    assert zasilacz.ilosc_finalna == 2.0
    assert zasilacz.match_quality == "ok"
    assert zasilacz.matched_product_id is not None


def test_run_ocr_task_bez_tasmy_led_nie_dodaje_zasilacza(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": [{"nazwa": "Wtyczka odbiornikowa 32A (niebieska) 1F", '
        '"ilosc_wydana": "1", "confidence": 98}]}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert len(document.items) == 1
    assert all(it.match_kod != "ZASILACZ LED 75W" for it in document.items)


def test_run_ocr_task_gniazdo_podwojne_podtynkowe_podwaja_ilosc(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Na zyczenie uzytkownika (2026-09-10): 'gniazdo podwojne ... podtynkowe' nie ma wlasnego
    kodu w Optimie - to fizycznie DWA pojedyncze gniazda podtynkowe z klapka, wiec ilosc musi
    zostac automatycznie podwojona (special_rules.py samo w sobie nie moze tego zrobic, bo
    MatchResult nie niesie ilosci - patrz _podwoj_ilosc_gniazda_podwojnego_podtynkowego)."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Gniazdo podwójne niemieckie białe podtynkowe", "ilosc_wydana": "1", "confidence": 98}'
        ']}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert len(document.items) == 3
    by_kod = {item.match_kod.strip(): item for item in document.items}
    gniazdo = by_kod["GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE NIEMIECKIE"]
    ramka = by_kod["RAMKA PODWÓJNA BIAŁA"]
    puszka = by_kod["PUSZKA INSTALACYJNA 2 POLOWA PODTYNKOWA"]
    assert gniazdo.ilosc_wydana == 2.0
    assert gniazdo.ilosc_finalna == 2.0
    assert ramka.ilosc_wydana == 1.0
    assert ramka.ilosc_finalna == 1.0
    assert puszka.ilosc_wydana == 1.0
    assert puszka.ilosc_finalna == 1.0
    assert ramka.form_note.startswith("Dodano automatycznie")
    assert puszka.form_note.startswith("Dodano automatycznie")


def test_run_ocr_task_gniazdo_podwojne_polskie_biale_plus_puszka_tworzy_pelny_zestaw(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Realny przypadek: 2 zestawy = 4 gniazda + 2 biale ramki + 2 puszki 2-polowe."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Gniazdo podwójne polskie białe podtynkowe + puszka", "ilosc_wydana": "2", "confidence": 98}'
        ']}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert len(document.items) == 3
    by_kod = {item.match_kod.strip(): item for item in document.items}
    assert by_kod["GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE POLSKIE"].ilosc_finalna == 4.0
    assert by_kod["RAMKA PODWÓJNA BIAŁA"].ilosc_finalna == 2.0
    assert by_kod["PUSZKA INSTALACYJNA 2 POLOWA PODTYNKOWA"].ilosc_finalna == 2.0


def test_run_ocr_task_gniazdo_podwojne_grafit_dodaje_ramke_antracyt(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Gniazdo podwójne polskie grafit podtynkowe", "ilosc_wydana": "1", "confidence": 98}'
        ']}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert len(document.items) == 3
    by_kod = {item.match_kod.strip(): item for item in document.items}
    assert by_kod["GNIAZDO 16A PODTYNKOWE Z KLAPKĄ GRAFIT POLSKIE"].ilosc_finalna == 2.0
    assert by_kod["RAMKA PODWÓJNA ANTRACYT"].ilosc_finalna == 1.0
    assert by_kod["PUSZKA INSTALACYJNA 2 POLOWA PODTYNKOWA"].ilosc_finalna == 1.0


def test_run_ocr_task_gniazdo_pojedyncze_podtynkowe_nie_podwaja_ilosci(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    ai_response = (
        '{"pozycje": ['
        '{"nazwa": "Gniazdo pojedyncze niemieckie białe podtynkowe", "ilosc_wydana": "1", "confidence": 98}'
        ']}'
    )
    with _mock_recognize(ai_response):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    item = document.items[0]
    assert item.match_kod == "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE NIEMIECKIE"
    assert item.ilosc_wydana == 1.0


def test_run_ocr_task_druga_proba_bez_wyniku_zostawia_ilosc_pusta(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":93.0}'
    ocr_response = (
        '{"pozycje": [{"nazwa": "Bojler 80 L", "ma_oznaczenie": true, "confidence": 90}]}'
    )
    verify_response = '{"pozycje":[{"id":"1","ilosc_wydana":null,"ilosc_zuzyta":null}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        # Cztery modele darmowe dostaja ten sam semantyczny brak wyniku; dopiero wtedy kontrola
        # konczy sie statusem "Bez wyniku" i pozostawia pole puste.
        new=AsyncMock(side_effect=[classify_response, ocr_response] + [verify_response] * 4),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].ilosc_wydana is None
    assert document.items[0].ilosc_finalna is None


def test_run_ocr_task_pelna_kontrola_wykrywa_przesuniecie_miedzy_niepodobnymi_etykietami(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_elektryka_json,
):
    """Realny przypadek produkcyjny (2026-09-18): przesuniecie wystapilo miedzy zupelnie
    NIEPODOBNYMI etykietami ("Szyna grzebieniowa widelkowa" -> "Koncowka tulejkowa TE 1,5-10").
    _check_full_document_consistency porownuje KAZDA pozycje z drugim, pelnym odczytem calego
    dokumentu - lapie tego typu przesuniecie niezaleznie od podobienstwa nazw."""
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"elektryka","confidence":98.0}'
    main_response = (
        '{"pozycje": [{"nazwa": "Końcówka tulejkowa TE 1,5-10", "ilosc_wydana": "13", "confidence": 98}]}'
    )
    confirm_response = (
        '{"pozycje": [{"nazwa": "Szyna grzebieniowa widełkowa", "ilosc_wydana": "13", "confidence": 98}]}'
    )
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, main_response]),
    ):
        run_ocr_task(document_id, db_session)

    # Główny wynik jest gotowy bez czekania na drugi pełny odczyt.
    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert len(document.items) == 1
    assert document.items[0].needs_review is False

    # Drugi odczyt jest osobnym zadaniem w tle i dopiero on dopisuje flagi.
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(return_value=confirm_response),
    ):
        run_full_document_verification_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    item = document.items[0]
    assert item.rozpoznana_nazwa == "Końcówka tulejkowa  TE 1,5-10"
    assert item.ilosc_wydana == 13.0
    assert item.needs_review is True
    assert item.ilosc_z_dodatkowej_kontroli is True

    trace_reasons = " ".join(e.get("reason") or "" for e in document.ai_trace)
    assert "Szyna grzebieniowa widełkowa" in trace_reasons
    assert any(
        e.get("stage") == "full_document_verification" and e.get("status") == "completed"
        for e in document.ai_trace
    )

    from app.modules.documents.models import OcrRowGroupFlagModel
    flags = db_session.query(OcrRowGroupFlagModel).filter(
        OcrRowGroupFlagModel.document_id == document_id,
    ).all()
    kinds = {f.kind for f in flags}
    assert kinds == {"full_reread_mismatch", "full_reread_missing"}


def test_run_ocr_task_pelna_kontrola_zgodnosc_nic_nie_zmienia(
    db_session, admin_user, mocked_storage, gemini_key_configured, baza_hydraulika_json,
):
    """"Zawór kątowy 1/2x3/4" to dokladny wiersz FORM_ROWS (snap "exact", nie nalezy do zadnej
    wykrytej grupy podobnych wierszy - patrz test_ocr_pipeline_hydraulika.py) - w przeciwienstwie
    do "Grzejnik 1800W" uzywanego w innych testach (off-form) nie ma wlasnego needs_review z
    glownego odczytu, wiec test czysto sprawdza zachowanie pelnej kontroli spojnosci."""
    import_catalog(db_session, baza_hydraulika_json, dzial="hydraulika")
    document_id = _create_document(db_session, admin_user)

    classify_response = '{"dzial":"hydraulika","confidence":95.0}'
    ocr_response = '{"pozycje": [{"nazwa": "Zawór kątowy 1/2x3/4", "ilosc_wydana": "1", "confidence": 98}]}'
    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(side_effect=[classify_response, ocr_response]),
    ):
        run_ocr_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    assert document.status == "done"
    assert document.items[0].needs_review is False

    with patch(
        "app.modules.ocr.providers.GeminiProvider.recognize",
        new=AsyncMock(return_value=ocr_response),
    ):
        run_full_document_verification_task(document_id, db_session)

    document = doc_repo.get_document(db_session, document_id)
    item = document.items[0]
    assert item.needs_review is False
    assert item.ilosc_z_dodatkowej_kontroli is False
    assert any(
        e.get("stage") == "full_document_verification" and e.get("status") == "completed"
        for e in document.ai_trace
    )


def test_auto_zasilacz_nie_dubluje_zasilacza_juz_odczytanego_z_kartki():
    """Jesli zasilacz 75W jest juz na papierowej wydawce, auto-regula tasmy nie dodaje drugiego."""
    items = [
        {"match_kod": "TAŚMA LED DO DEKORÓW", "rozpoznana_nazwa": "Taśma LED 5M"},
        {"match_kod": "ZASILACZ LED 75W", "rozpoznana_nazwa": "Zasilacz do LED", "ilosc_finalna": 1.0},
    ]

    _append_auto_zasilacz_led(items, "elektryka", session=None)

    zasilacze = [it for it in items if it.get("match_kod") == "ZASILACZ LED 75W"]
    assert len(zasilacze) == 1
    assert zasilacze[0]["rozpoznana_nazwa"] == "Zasilacz do LED"
    assert zasilacze[0]["ilosc_finalna"] == 1.0


def test_background_review_pomija_pozycje_dodana_automatycznie():
    row = SimpleNamespace(
        form_note="Dodano automatycznie - 1 szt. za każde wystąpienie taśmy LED w tym dokumencie.",
        rozpoznana_nazwa="Zasilacz LED 75W",
        ilosc_wydana=None,
        ilosc_zuzyta=None,
        match_kod="ZASILACZ LED 75W",
        uwagi="",
        needs_review=False,
        ilosc_z_dodatkowej_kontroli=False,
    )
    assert _background_review_item(row) is None


def test_background_review_cofa_mnoznik_gniazda_przed_porownaniem_z_papierem():
    row = SimpleNamespace(
        form_note="",
        rozpoznana_nazwa="Gniazdo podwójne białe niemieckie podtynkowe",
        ilosc_wydana=4.0,
        ilosc_zuzyta=2.0,
        match_kod="GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE NIEMIECKIE",
        uwagi="Gniazdo podwójne = 2x gniazdo pojedyncze podtynkowe z klapką - ilość podwojona automatycznie.",
        needs_review=False,
        ilosc_z_dodatkowej_kontroli=False,
    )

    review = _background_review_item(row)

    assert review is not None
    assert review["ilosc_wydana"] == 2.0
    assert review["ilosc_zuzyta"] == 1.0
