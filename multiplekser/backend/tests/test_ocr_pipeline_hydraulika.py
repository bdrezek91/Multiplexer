"""Testy Kroku Hydraulika-3: recognize_document_hydraulika() - odpowiednik testow OCR Elektryki,
katalog z fixture JSON (bez bazy), HTTP zamockowany."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
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
