import httpx
import pytest
from unittest.mock import AsyncMock, patch

from app.modules.ocr.providers import GroqProvider, OCRProviderError


@pytest.mark.asyncio
async def test_groq_provider_wysyla_obrazy_i_json_mode():
    response = httpx.Response(
        200,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
        json={"choices": [{"message": {"content": '{"pozycje":[]}'}}]},
    )
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.__aexit__.return_value = None
    client.post.return_value = response

    with patch("app.modules.ocr.providers.httpx.AsyncClient", return_value=client):
        text = await GroqProvider().recognize(
            files=[(b"abc", "image/jpeg"), (b"def", "image/png")],
            model="qwen/qwen3.8-27b",
            api_key="test-secret",
            prompt="OCR",
        )

    assert text == '{"pozycje":[]}'
    kwargs = client.post.await_args.kwargs
    body = kwargs["json"]
    assert body["model"] == "qwen/qwen3.8-27b"
    assert body["response_format"] == {"type": "json_object"}
    assert len(body["messages"][0]["content"]) == 3
    assert kwargs["headers"]["Authorization"] == "Bearer test-secret"


@pytest.mark.asyncio
async def test_groq_provider_odrzuca_wiecej_niz_3_obrazy():
    with pytest.raises(OCRProviderError, match="maksymalnie 3 obrazy"):
        await GroqProvider().recognize(
            files=[(b"x", "image/jpeg")] * 4,
            model="qwen/qwen3.8-27b",
            api_key="x",
            prompt="OCR",
        )
