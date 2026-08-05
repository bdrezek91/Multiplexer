"""Testy OpenAIProvider - ostatni krok w default_ocr_chain() (patrz ocr/chain.py), uzywany
WYLACZNIE gdy wszystkie kroki Gemini zawioda. HTTP zamockowany (bez sieci, bez kosztow) -
odpowiedz w formacie Responses API (nie starsze Chat Completions), bo ta obsluguje natywnie
zarowno obrazy jak i PDF."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.modules.ocr.providers import OCRProviderError, OpenAIProvider


def _fake_response(status_code=200, json_data=None, text=""):
    kwargs = {"request": httpx.Request("POST", "https://example.com")}
    if json_data is not None:
        kwargs["json"] = json_data
    else:
        kwargs["text"] = text
    return httpx.Response(status_code, **kwargs)


def _responses_payload(text: str) -> dict:
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


async def test_parsuje_pojedynczy_fragment_tekstu():
    fake = _fake_response(json_data=_responses_payload('{"pozycje": []}'))
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await OpenAIProvider().recognize(
            files=[(b"dane", "image/jpeg")], model="gpt-4o-mini", api_key="klucz", prompt="prompt"
        )
    assert text == '{"pozycje": []}'


async def test_laczy_wiele_czesci_tekstu_znakiem_nowej_linii():
    fake = _fake_response(json_data={
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "a"}, {"type": "output_text", "text": "b"},
        ]}],
    })
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await OpenAIProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")
    assert text == "a\nb"


async def test_brak_output_zwraca_pusty_tekst():
    fake = _fake_response(json_data={"output": []})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        text = await OpenAIProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")
    assert text == ""


async def test_blad_http_rzuca_ocr_provider_error_z_kodem_statusu():
    fake = _fake_response(status_code=429, text="rate limited")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        with pytest.raises(OCRProviderError, match="429") as exc_info:
            await OpenAIProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")
    assert exc_info.value.status_code == 429


async def test_timeout_rzuca_ocr_provider_error():
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
        with pytest.raises(OCRProviderError, match="Timeout"):
            await OpenAIProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="k", prompt="p")


async def test_obraz_wysylany_jako_input_image_pdf_jako_input_file():
    fake = _fake_response(json_data=_responses_payload("ok"))
    mock_post = AsyncMock(return_value=fake)
    with patch("httpx.AsyncClient.post", new=mock_post):
        await OpenAIProvider().recognize(
            files=[(b"obrazek", "image/jpeg"), (b"%PDF-1.4", "application/pdf")],
            model="m", api_key="k", prompt="p",
        )

    sent_body = mock_post.call_args.kwargs["json"]
    content = sent_body["input"][0]["content"]
    assert content[0]["type"] == "input_image"
    assert content[0]["image_url"].startswith("data:image/jpeg;base64,")
    assert content[1]["type"] == "input_file"
    assert content[1]["file_data"].startswith("data:application/pdf;base64,")
    # Tekst prompta zawsze na koncu, po wszystkich plikach.
    assert content[-1] == {"type": "input_text", "text": "p"}


async def test_wysyla_klucz_w_naglowku_authorization():
    fake = _fake_response(json_data=_responses_payload("ok"))
    mock_post = AsyncMock(return_value=fake)
    with patch("httpx.AsyncClient.post", new=mock_post):
        await OpenAIProvider().recognize(files=[(b"dane", "image/jpeg")], model="m", api_key="sekretny-klucz", prompt="p")

    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer sekretny-klucz"
