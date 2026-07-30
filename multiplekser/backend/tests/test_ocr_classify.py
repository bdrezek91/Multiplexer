"""Testy Kroku Hydraulika-3: classify_document() - Krok A dwuetapowego wywolania Gemini
(patrz docs/MIGRATION_PLAN_HYDRAULIKA.md, sekcja 4.5). HTTP zamockowany, jak w test_ocr_provider_gemini.py."""
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.ocr.classify import classify_document


def _mock_recognize(response_text: str):
    return patch("app.modules.ocr.providers.GeminiProvider.recognize", new=AsyncMock(return_value=response_text))


async def test_klasyfikuje_elektryke(gemini_key_configured):
    with _mock_recognize('{"dzial":"elektryka","confidence":97.5}'):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "elektryka"
    assert result.confidence == 97.5
    assert result.fallback is False


async def test_klasyfikuje_hydraulike(gemini_key_configured):
    with _mock_recognize('{"dzial":"hydraulika","confidence":88.0}'):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "hydraulika"
    assert result.confidence == 88.0


async def test_odpowiedz_z_markdown_ogrodzeniem_dziala(gemini_key_configured):
    with _mock_recognize('```json\n{"dzial":"hydraulika","confidence":80}\n```'):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "hydraulika"


async def test_niesparsowalna_odpowiedz_ma_bezpieczny_fallback_na_elektryke(gemini_key_configured):
    """Uzytkownik nie chce recznego przelacznika - klasyfikacja musi byc w pelni automatyczna.
    Gdy model nie zwroci poprawnego JSON, fallback na jedyny dzial obslugiwany PRZED tym
    krokiem (elektryka), zeby nie zmienic dotychczasowego zachowania w niejednoznacznym przypadku."""
    with _mock_recognize("Przepraszam, nie rozumiem polecenia."):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "elektryka"
    assert result.confidence == 0.0
    assert result.fallback is True


async def test_nieznana_wartosc_dzial_ma_fallback(gemini_key_configured):
    with _mock_recognize('{"dzial":"stolarka","confidence":90}'):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "elektryka"
    assert result.fallback is True


async def test_brak_pola_confidence_domyslnie_zero(gemini_key_configured):
    with _mock_recognize('{"dzial":"hydraulika"}'):
        result = await classify_document(b"dane", "image/jpeg")
    assert result.dzial == "hydraulika"
    assert result.confidence == 0.0
