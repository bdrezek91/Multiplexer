"""No-network proof that fallback reuses one HTTP client; prompt/requests unchanged."""
import asyncio
import httpx
from unittest.mock import patch
from app.modules.ocr.chain import OCRChainStep, run_ocr_chain
from app.modules.ocr.providers import GeminiProvider


def test_gemini_http_pool_preserves_model_payload_and_reuses_connection():
    created=[]
    class Client:
        def __init__(self,**kwargs):self.requests=[];created.append(self)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,headers=None,json=None):
            self.requests.append((url,headers,json))
            if len(self.requests)==1:
                return httpx.Response(429, text='model quota exceeded')
            return httpx.Response(200,json={'candidates':[{'content':{'parts':[{'text':'{"pozycje":[{"nazwa":"Wago","ilosc_wydana":1}]}'}]}}]})
    provider=GeminiProvider()
    steps=[OCRChainStep('FREE1',provider,'gemini-3.6-flash','K1',2),
           OCRChainStep('FREE2',provider,'gemini-3.6-flash','K2',2)]
    with patch('app.modules.ocr.providers.httpx.AsyncClient',side_effect=Client):
        result=asyncio.run(run_ocr_chain([(b'JPEG_DATA','image/jpeg')], 'Read quantities',
               chain=steps,response_validator=lambda t: t.startswith('{')))
    assert result.used_label=='FREE2'
    assert len(created)==1, 'Fallback must use a single HTTP connection pool'
    assert len(created[0].requests)==2
    assert [req[1]['x-goog-api-key'] for req in created[0].requests]==['K1','K2']
    assert [req[2]['generationConfig']['temperature'] for req in created[0].requests]==[0,0]
    assert created[0].requests[0][2]['contents']==created[0].requests[1][2]['contents']
    assert created[0].requests[0][2]['contents'][0]['parts'][-1]['text']=='Read quantities'
