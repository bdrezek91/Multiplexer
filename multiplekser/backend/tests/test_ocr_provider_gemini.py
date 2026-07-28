"""Testy Etapu 6: GeminiProvider - port geminiRecognize() z monolitu. HTTP zamockowany (bez sieci,
bez kosztow) - test na prawdziwym kluczu jest opcjonalny, patrz test_ocr_gemini_live.py."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.modules.ocr.providers import GeminiProvider, OCRProviderError


def _fake_response(status_code=200, json_data=None, text=""):
    kwargs = {"request": httpx.Request("POST", "https://example.com")}
    if json_data is not None:
        kwargs["json"] = json_data
    else:
        kwargs["text"] = text
    return httpx.Response(status_code, **kwargs)


async def test_parsuje_pojedynczy_fragment_tekstu():
    fake = _fake_response(json_data={"candidates": [{"content": {"parts": [{"text": '{"pozycje": []}'}]}}]})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await GeminiProvider().recognize(
            file_bytes=b"dane", mime="image/jpeg", model="gemini-3.6-flash", api_key="klucz", prompt="prompt"
        )
    assert text == '{"pozycje": []}'


async def test_laczy_wiele_czesci_tekstu_znakiem_nowej_linii():
    fake = _fake_response(json_data={"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await GeminiProvider().recognize(
            file_bytes=b"dane", mime="image/jpeg", model="m", api_key="k", prompt="p"
        )
    assert text == "a\nb"


async def test_brak_kandydatow_zwraca_pusty_tekst():
    fake = _fake_response(json_data={"candidates": []})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await GeminiProvider().recognize(
            file_bytes=b"dane", mime="image/jpeg", model="m", api_key="k", prompt="p"
        )
    assert text == ""


async def test_blad_http_rzuca_ocr_provider_error_z_kodem_statusu():
    fake = _fake_response(status_code=429, text="rate limited")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        with pytest.raises(OCRProviderError, match="429"):
            await GeminiProvider().recognize(file_bytes=b"dane", mime="image/jpeg", model="m", api_key="k", prompt="p")


async def test_timeout_rzuca_ocr_provider_error():
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
        with pytest.raises(OCRProviderError, match="Timeout"):
            await GeminiProvider().recognize(file_bytes=b"dane", mime="image/jpeg", model="m", api_key="k", prompt="p")
