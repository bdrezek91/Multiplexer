"""Regression for incident 2026-10-14: 3.6 must not eat 26s before usable 3.5."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from app.core.config import settings
from app.modules.documents.auto_v3 import recognize_gemini_primary
from app.modules.ocr import classify,pipeline_elektryka
from app.modules.ocr.chain import run_ocr_chain
from app.modules.ocr.providers import GeminiProvider,OCRProviderError
from app.modules.products import Catalog


@pytest.mark.parametrize('first_key_rejected',[False,True])
def test_reliably_working_gemini_35_ocr_is_used_before_503_model(first_key_rejected):
    calls=[];trace=[]
    async def fake_recognize(self,*,files,model,api_key,prompt,thinking_level='low'):
        calls.append((model,api_key))
        if model=='gemini-3.6-flash':
            raise OCRProviderError('simulated slow 503',status_code=503)
        if first_key_rejected and api_key=='FREE1':
            raise OCRProviderError('simulated 429',status_code=429)
        return '{"pozycje":[{"nazwa":"Wago","ilosc_wydana":2}]}'

    async def read_electric(files,catalog,rules,magazyn,*,chain,event_callback=None,cooldown_store=None):
        result=await run_ocr_chain(files,'existing OCR prompt unmodified',chain=chain,
                      response_validator=lambda x:'"pozycje"' in x,
                      event_callback=event_callback,cooldown_store=cooldown_store,
                      log_context={'ai_stage':'full_ocr_elektryka'})
        return SimpleNamespace(pozycje=[SimpleNamespace(rozpoznana_nazwa='Wago',ilosc_wydana=2)],
                               used_provider=result.used_label)

    with patch.object(settings,'gemini_api_key_free','FREE1'), \
         patch.object(settings,'gemini_api_key_free_2','FREE2'), \
         patch.object(settings,'gemini_api_key_paid','PAID_FORBIDDEN'), \
         patch.object(classify,'classify_document',new_callable=AsyncMock) as cls, \
         patch.object(pipeline_elektryka,'recognize_document',side_effect=read_electric), \
         patch.object(GeminiProvider,'recognize',fake_recognize), \
         patch('app.modules.ocr.image.classification_header_preview',return_value=b'header'), \
         patch.object(Catalog,'from_db',return_value=object()), \
         patch('app.modules.matcher.rules_from_db',return_value=[]):
        cls.return_value=SimpleNamespace(dzial='elektryka',confidence=94,fallback=False,
                             used_provider='AUTO Gemini gemini-3.5-flash-lite darmowy')
        _,dzial,recognition,_=recognize_gemini_primary(
            [(b'PAGE','image/jpeg')],object(),'Zabrze',event_callback=trace.append)
    assert dzial=='elektryka'
    assert len(recognition.pozycje)==1
    assert calls==([('gemini-3.5-flash-lite','FREE1'),('gemini-3.5-flash-lite','FREE2')]
                   if first_key_rejected else [('gemini-3.5-flash-lite','FREE1')])
    assert all(key!='PAID_FORBIDDEN' and model!='gemini-3.6-flash' for model,key in calls)
    assert trace[-1]['status']=='selected'
