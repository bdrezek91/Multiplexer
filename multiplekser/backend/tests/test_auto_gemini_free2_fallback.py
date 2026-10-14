"""Fake-quota regression: FREE1 errors must not block FREE2.

No real API keys, Redis production keys, or uploaded files used.
"""
import asyncio
import time

import pytest

from app.modules.ocr.chain import OCRChainStep, run_ocr_chain
from app.modules.ocr.cooldown import RedisOCRCooldownStore
from app.modules.ocr.providers import GeminiProvider, OCRProviderError


class MemoryRedis:
    def __init__(self):
        self.values={}
        self.ttls={}
    def ttl(self,key):return self.ttls.get(key,-2)
    def incr(self,key):
        self.values[key]=int(self.values.get(key,0))+1
        return self.values[key]
    def expire(self,key,seconds):self.ttls[key]=seconds
    def set(self,key,value,ex):
        self.values[key]=value
        self.ttls[key]=ex
    def delete(self,*keys):
        for key in keys:
            self.values.pop(key,None)
            self.ttls.pop(key,None)


@pytest.mark.parametrize('failure',[429,503,'timeout'])
def test_free1_failure_switches_to_free2_without_trying_other_free1_models(failure):
    attempts=[]; events=[];store=RedisOCRCooldownStore(MemoryRedis())
    model='gemini-3.6-flash'
    label_1=f'AUTO Gemini {model} darmowy'
    label_2=f'AUTO Gemini {model} darmowy FREE2'
    class FakeGemini(GeminiProvider):
        async def recognize(self,*,files,model,api_key,prompt,thinking_level):
            attempts.append(api_key)
            if api_key=='FREE-1':
                if failure=='timeout':await asyncio.sleep(.15)
                raise OCRProviderError('simulated quota/service failure',status_code=failure)
            return '{"pozycje":[{"nazwa":"TEST","ilosc_wydana":1}]}'
    provider=FakeGemini()
    chain=[
        OCRChainStep(label_1,provider,model,'FREE-1',.025),
        OCRChainStep(label_2,provider,model,'FREE-2',.025),
        OCRChainStep('AUTO Gemini other model darmowy',provider,'gemini-3.1-flash-lite','FREE-1',.025),
    ]
    start=time.perf_counter()
    result=asyncio.run(run_ocr_chain([(b'DUMMY','image/jpeg')],'test',chain=chain,
                                    cooldown_store=store,event_callback=events.append))
    elapsed=time.perf_counter()-start
    assert attempts==['FREE-1','FREE-2']
    assert result.used_label==label_2
    assert elapsed < .12
    assert store.remaining_seconds(label_1)>0
    assert store.remaining_seconds(label_2)==0
    statuses=[(x['status'],x['label']) for x in events if x.get('label')]
    assert statuses[0]==('attempt',label_1)
    assert ('rejected',label_1) in statuses
    assert ('selected',label_2) in statuses
    # Another document should SKIP blocked FREE1 and immediately use FREE2.
    attempts.clear()
    follow=asyncio.run(run_ocr_chain([(b'DUMMY','image/jpeg')],'test',chain=chain,
                                   cooldown_store=store))
    assert follow.used_label==label_2
    assert attempts==['FREE-2']


def test_free2_cooldown_does_not_affect_free1():
    store=RedisOCRCooldownStore(MemoryRedis())
    a='AUTO Gemini gemini-3.6-flash darmowy'
    b=a+' FREE2'
    assert store.record_rate_limit(a)==10
    assert store.remaining_seconds(a)==600
    assert store.remaining_seconds(b)==0
    assert store.record_unavailable(b)==3
    assert store.remaining_seconds(b)==180
    assert store.remaining_seconds(a)==600
