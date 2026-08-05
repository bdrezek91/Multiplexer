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
            files=[(b"dane", "image/jpeg")], model="gemini-3.6-flash", api_key="klucz", prompt="prompt"
        )
    assert text == '{"pozycje": []}'


async def test_laczy_wiele_czesci_tekstu_znakiem_nowej_linii():
    fake = _fake_response(json_data={"candidates": [{"content": {"parts": [{"text": "a"}, {"text": "b"}]}}]})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await GeminiProvider().recognize(
            files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p"
        )
    assert text == "a\nb"


async def test_brak_kandydatow_zwraca_pusty_tekst():
    fake = _fake_response(json_data={"candidates": []})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await GeminiProvider().recognize(
            files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p"
        )
    assert text == ""


async def test_blad_http_rzuca_ocr_provider_error_z_kodem_statusu():
    fake = _fake_response(status_code=429, text="rate limited")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        with pytest.raises(OCRProviderError, match="429") as exc_info:
            await GeminiProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")
    assert exc_info.value.status_code == 429


async def test_timeout_rzuca_ocr_provider_error():
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
        with pytest.raises(OCRProviderError, match="Timeout"):
            await GeminiProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")


async def test_wiele_plikow_buduje_wiele_czesci_inline_data():
    """Realna potrzeba (patrz historia czatu): dwa osobne zdjecia z telefonu tej samej
    papierowej wydawki musza trafic do Gemini w JEDNYM zapytaniu, jako dwie osobne czesci
    "inline_data" (Gemini wspiera to natywnie) - nie dwa osobne zapytania."""
    fake = _fake_response(json_data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    mock_post = AsyncMock(return_value=fake)
    with patch("httpx.AsyncClient.post", new=mock_post):
        await GeminiProvider().recognize(
            files=[(b"strona1", "image/jpeg"), (b"strona2", "image/png")],
            model="m", api_key="k", prompt="p",
        )

    sent_body = mock_post.call_args.kwargs["json"]
    parts = sent_body["contents"][0]["parts"]
    inline_parts = [p for p in parts if "inline_data" in p]
    assert len(inline_parts) == 2
    assert inline_parts[0]["inline_data"]["mime_type"] == "image/jpeg"
    assert inline_parts[1]["inline_data"]["mime_type"] == "image/png"
    # Tekst prompta zawsze na koncu, po wszystkich obrazach.
    assert parts[-1] == {"text": "p"}
