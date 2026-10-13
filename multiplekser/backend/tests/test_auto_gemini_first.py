"""AUTO Gemini-first regression: free OCR, data parity, no paid keys."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.modules.documents.auto_v3 import (
    AmbiguousDepartment, recognize_gemini_primary,
)
from app.modules.ocr import classify, pipeline_elektryka, pipeline_hydraulika
from app.modules.products import Catalog


@pytest.mark.parametrize("department",["hydraulika","elektryka"])
def test_primary_gemini_three_free_models_and_preserves_header(department):
    classified=SimpleNamespace(dzial=department,confidence=94.0,fallback=False,used_provider="AUTO Gemini gemini-3.1-flash-lite darmowy")
    rows=[SimpleNamespace(rozpoznana_nazwa="Test")]
    expected=SimpleNamespace(
        pozycje=rows,numer_projektu="126/07",
        pracownik="Dawid",numer_plomby=None,
        used_provider="Gemini AUTO (darmowy)",rejected_count=0,
    )
    with patch.object(settings,"gemini_api_key_free","KEY-FREE"), \
         patch.object(settings,"gemini_api_key_paid","KEY-PAID"), \
         patch.object(classify,"classify_document",new_callable=AsyncMock) as cls, \
         patch.object(pipeline_hydraulika,"recognize_document_hydraulika",new_callable=AsyncMock) as hyd, \
         patch.object(pipeline_elektryka,"recognize_document",new_callable=AsyncMock) as elec, \
         patch("app.modules.ocr.image.classification_header_preview",return_value=b"header"), \
         patch.object(Catalog,"from_db",return_value=object()) as catalog, \
         patch("app.modules.matcher.rules_from_db",return_value=[]) as rules:
        cls.return_value=classified
        hyd.return_value=expected
        elec.return_value=expected
        res,dzial,output,timings=recognize_gemini_primary(
            [(b"PAGE","image/jpeg")],object(),"Zabrze",
        )
    assert dzial==department
    assert res.confidence==94
    assert output.pracownik=="Dawid"
    assert output.numer_projektu=="126/07"
    assert output is expected
    assert "timing_classification" in timings and "timing_ocr_matcher" in timings
    cls_chain=cls.await_args.kwargs["chain"]
    pipeline=hyd if department=="hydraulika" else elec
    ocr_chain=pipeline.await_args.kwargs["chain"]
    for chain in (cls_chain,ocr_chain):
        assert len(chain)==3
        assert all(step.api_key=="KEY-FREE" for step in chain)
        assert all(step.api_key!="KEY-PAID" for step in chain)
        assert {step.model for step in chain} == {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"}
    assert ocr_chain[0].model == "gemini-3.1-flash-lite"
    if department=="hydraulika":
        elec.assert_not_awaited()
        rules.assert_not_called()
    else:
        hyd.assert_not_awaited()
    catalog.assert_called_once()


def test_no_free_key_causes_fallback_without_paid_calls():
    with patch.object(settings,"gemini_api_key_free",None), \
         patch.object(settings,"gemini_api_key_paid","KEY-PAID"), \
         patch.object(classify,"classify_document",new_callable=AsyncMock) as cls:
        with pytest.raises(RuntimeError,match="darmowy klucz"):
            recognize_gemini_primary([(b"PAGE","image/jpeg")],object(),"Zabrze")
        cls.assert_not_awaited()


def test_uncertain_classification_does_not_choose_random_catalog():
    with patch.object(settings,"gemini_api_key_free","KEY-FREE"), \
         patch.object(classify,"classify_document",new_callable=AsyncMock) as cls, \
         patch("app.modules.ocr.image.classification_header_preview",return_value=b"header"), \
         patch.object(Catalog,"from_db") as catalog:
        cls.return_value=SimpleNamespace(dzial="elektryka",fallback=True,confidence=0)
        with pytest.raises(AmbiguousDepartment):
            recognize_gemini_primary([(b"PAGE","image/jpeg")],object(),"Zabrze")
        catalog.assert_not_called()


def test_gemini_timeout_is_not_retried_on_paid_key():
    from app.modules.ocr.chain import AllProvidersFailedError
    with patch.object(settings,"gemini_api_key_free","KEY-FREE"), \
         patch.object(settings,"gemini_api_key_paid","KEY-PAID"), \
         patch.object(classify,"classify_document",new_callable=AsyncMock) as cls, \
         patch("app.modules.ocr.image.classification_header_preview",return_value=b"header"):
        cls.side_effect=AllProvidersFailedError([],TimeoutError("Gemini timeout"))
        with pytest.raises(AllProvidersFailedError):
            recognize_gemini_primary([(b"PAGE","image/jpeg")],object(),"Zabrze")
        assert cls.await_count==1
        assert len(cls.await_args.kwargs["chain"]) == 3
        assert all(x.api_key=="KEY-FREE" for x in cls.await_args.kwargs["chain"])


@pytest.mark.parametrize("first_failure",["429","low_confidence"])
def test_gemini_chain_tries_second_free_model_without_using_claude(first_failure):
    import asyncio
    from app.modules.ocr.chain import OCRChainStep
    from app.modules.ocr.classify import classify_document
    from app.modules.ocr.providers import GeminiProvider, OCRProviderError

    calls=[]
    events=[]
    async def fake_recognize(self, *, files, model, api_key, prompt, thinking_level):
        calls.append((model,api_key))
        if model=="gemini-3.5-flash-lite":
            if first_failure=="429":
                raise OCRProviderError("quota exceeded",status_code=429)
            return '{"dzial":"hydraulika","confidence":25}'
        return '{"dzial":"hydraulika","confidence":94}'
    provider=GeminiProvider()
    chain=[
        OCRChainStep("AUTO Gemini gemini-3.5-flash-lite darmowy",provider,
                     "gemini-3.5-flash-lite","FREE",1),
        OCRChainStep("AUTO Gemini gemini-3.1-flash-lite darmowy",provider,
                     "gemini-3.1-flash-lite","FREE",1),
    ]
    class DummyCooldown:
        def remaining_seconds(self,step_label):return 0
        def record_rate_limit(self,step_label):return 10
        def reset(self,step_label):pass
    with patch.object(GeminiProvider,"recognize",fake_recognize):
        result=asyncio.run(classify_document(
            [(b"header","image/jpeg")],chain=chain,min_confidence=65,
            cooldown_store=DummyCooldown(),event_callback=events.append,
        ))
    assert result.dzial=="hydraulika"
    assert result.confidence==94
    assert "3.1-flash-lite" in result.used_provider
    assert calls==[("gemini-3.5-flash-lite","FREE"),("gemini-3.1-flash-lite","FREE")]
    assert [e["status"] for e in events if e["status"] in {"rejected","selected"}]==[
        "rejected","selected",
    ]
