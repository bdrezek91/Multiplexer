"""Test provider Cloudflare bez prawdziwego wywolania API."""
import asyncio
from app.core.config import settings
from app.modules.ocr.providers import CloudflareProvider


def test_cloudflare_vision_contract(monkeypatch):
    seen={}

    class FakeResponse:
        status_code=200
        def json(self):
            return {"success":True,"result":{"choices":[{"message":{"content":'{"pozycje":[]}'}}]}}

    class FakeClient:
        def __init__(self,timeout):
            assert timeout >= 90
        async def __aenter__(self):
            return self
        async def __aexit__(self,exc_type,exc,tb):
            return False
        async def post(self,url,headers,json):
            seen["url"]=url
            seen["body"]=json
            assert headers["Authorization"] == "Bearer FAKE"
            return FakeResponse()

    monkeypatch.setattr(settings, "cloudflare_account_id", "test-account")
    monkeypatch.setattr("app.modules.ocr.providers.httpx.AsyncClient", FakeClient)
    result=asyncio.run(CloudflareProvider().recognize(
        files=[(b"fake-image", "image/jpeg")],
        model="@cf/google/gemma-4-26b-a4b-it",
        api_key="FAKE",
        prompt="Odczytaj tresc",
    ))
    assert result == '{"pozycje":[]}'
    assert seen["url"].endswith("/ai/run/@cf/google/gemma-4-26b-a4b-it")
    assert seen["body"]["chat_template_kwargs"]["enable_thinking"] is False
    content=seen["body"]["messages"][0]["content"]
    assert content[0]["text"] == "Odczytaj tresc"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_shadow_prompt_has_quantities_and_empty_row_protection():
    from app.modules.documents.cloudflare_shadow import _CLOUDFLARE_PROMPT
    assert "ilosc_wydana" in _CLOUDFLARE_PROMPT
    assert "ilosc_zuzyta" in _CLOUDFLARE_PROMPT
    assert "Puste" in _CLOUDFLARE_PROMPT
