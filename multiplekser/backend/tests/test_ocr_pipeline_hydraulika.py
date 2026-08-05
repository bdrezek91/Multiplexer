"""Testy Kroku Hydraulika-3: recognize_document_hydraulika() - odpowiednik testow OCR Elektryki,
katalog z fixture JSON (bez bazy), HTTP zamockowany."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import GeminiProvider
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_hydraulika.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db, dzial="hydraulika")


def _mock_recognize(response_text: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=response_text))


async def test_pozycja_z_glownego_formularza_dopasowana_ok(catalog, gemini_key_configured):
    ai_response = (
        '{"numer_projektu": "12/05/26", "pozycje": ['
        '{"nazwa": "Zawór kątowy 1/2x3/4", "ilosc_wydana": "2", "ilosc_zuzyta": null, "confidence": 98}'
        "]}"
    )
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    assert result.numer_projektu == "12/05/2026"
    assert len(result.pozycje) == 1
    item = result.pozycje[0]
    # FORM_ROWS ma tu podwojna spacje w zrodle (monolit) - wiernie zachowana w porcie.
    assert item.rozpoznana_nazwa == "Zawór  kątowy 1/2x3/4"
    assert item.match.kod == "ZAWÓR KĄTOWY 1/2X3/4"
    assert item.needs_review is False
    assert item.off_form is False


async def test_pozycja_z_bazy_dodatkowej_oznaczona_do_weryfikacji(catalog, gemini_key_configured):
    ai_response = '{"pozycje": [{"nazwa": "Grzejnik 1000W", "ilosc_wydana": "1"}]}'
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    item = result.pozycje[0]
    assert item.rozpoznana_nazwa == "Grzejnik 1000W"
    assert item.needs_review is True
    assert item.off_form is False
    assert "baza dodatkowa" in item.form_note


async def test_pozycja_spoza_obu_list_jest_off_form(catalog, gemini_key_configured):
    ai_response = '{"pozycje": [{"nazwa": "Zupelnie nieznany towar XYZ", "ilosc_wydana": "1"}]}'
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    item = result.pozycje[0]
    assert item.off_form is True
    assert item.needs_review is True


async def test_niepoprawna_pozycja_jest_odrzucana(catalog, gemini_key_configured):
    ai_response = '{"pozycje": [{"nazwa": "X"}, {"nazwa": "Bojler 80 L", "ilosc_wydana": "1"}]}'
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    assert result.rejected_count == 1
    assert len(result.pozycje) == 1
    assert result.pozycje[0].match.kod == "BOJLER 80 L"


async def test_pusty_wiersz_jest_pomijany_a_nieczytelny_oznaczony_zostaje(catalog, gemini_key_configured):
    ai_response = (
        '{"pozycje": ['
        '{"nazwa":"Rozdzielacz 2 sekcje","ilosc_wydana":null,"ilosc_zuzyta":null},'
        '{"nazwa":"Bojler 80 L","ilosc_wydana":null,"ilosc_zuzyta":null,'
        '"ma_oznaczenie":true},'
        '{"nazwa":"Grzejnik 1000W","ilosc_wydana":1,"ilosc_zuzyta":null}'
        ']}'
    )
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    assert [item.rozpoznana_nazwa for item in result.pozycje] == ["Bojler 80 L", "Grzejnik 1000W"]
    assert result.pozycje[0].ilosc_wydana is None
    assert result.pozycje[0].ilosc_zuzyta is None


async def test_lokalnie_wykryty_trojnik_pominiety_przez_ai_trafia_do_kontroli(
    catalog, gemini_key_configured, monkeypatch,
):
    ai_response = '{"pozycje":[{"nazwa":"Bateria umywalkowa","ilosc_wydana":1}]}'
    monkeypatch.setattr(
        "app.modules.ocr.pipeline_hydraulika.discover_marked_hydraulika_rows",
        lambda files: ["Bateria umywalkowa", "Trójnik PP 20"],
    )
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    assert [item.rozpoznana_nazwa for item in result.pozycje] == [
        "Bateria umywalkowa", "Trójnik PP 20",
    ]
    assert result.pozycje[1].ilosc_wydana is None
    assert result.pozycje[1].ilosc_zuzyta is None


async def test_waz_20_i_30_cm_pozostaja_dwoma_roznymi_pozycjami(catalog, gemini_key_configured):
    ai_response = (
        '{"pozycje":['
        '{"nazwa":"Wąż 1/2x1/2 cala 20 cm","ilosc_wydana":1},'
        '{"nazwa":"Wąż 1/2x1/2 cala 30 cm","ilosc_wydana":2}'
        ']}'
    )
    with _mock_recognize(ai_response):
        result = await recognize_document_hydraulika([(b"dane", "image/jpeg")], catalog)

    assert [item.rozpoznana_nazwa for item in result.pozycje] == [
        "Wąż 1/2x1/2 cala 20 cm", "Wąż 1/2x1/2 cala 30 cm",
    ]


async def test_niepoprawny_json_pierwszego_modelu_uruchamia_drugi(catalog):
    mock_recognize = AsyncMock(side_effect=[
        "to nie jest JSON",
        '{"pozycje": [{"nazwa": "Bojler 80 L", "ilosc_wydana": "1"}]}',
    ])
    provider = GeminiProvider()
    chain = [
        OCRChainStep("Pierwszy", provider, "model-a", "klucz-1"),
        OCRChainStep("Drugi", provider, "model-b", "klucz-2"),
    ]
    with patch("app.modules.ocr.providers.GeminiProvider.recognize", new=mock_recognize):
        result = await recognize_document_hydraulika(
            [(b"dane", "image/jpeg")], catalog, chain=chain,
        )
    assert result.used_provider == "Drugi"
    assert result.pozycje[0].match.kod == "BOJLER 80 L"
    assert mock_recognize.await_count == 2
