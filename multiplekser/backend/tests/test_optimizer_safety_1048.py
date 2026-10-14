"""Regression gates: Gemini-only, exact original matching, manual review on timeout."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import pytest

from app.core.config import settings
from app.modules.ocr.chain import quantity_verification_chain, OCRChainStep
from app.modules.ocr.cooldown import RedisOCRCooldownStore
from app.modules.documents.ocr_processing import flag_unverified_quantities
from app.modules.documents.auto_v3 import recognize_gemini_primary
from app.modules.ocr import classify, pipeline_elektryka, pipeline_hydraulika
from app.modules.products import Catalog


@pytest.mark.parametrize('department',['hydraulika','elektryka'])
def test_quantity_model_order_and_both_free_projects(department):
    with patch.object(settings,'gemini_api_key_free','FREE1'), \
         patch.object(settings,'gemini_api_key_free_2','FREE2'), \
         patch.object(settings,'gemini_api_key_paid','PAID'):
        chain=quantity_verification_chain(department)
        assert len(chain)==10
        assert [x.api_key for x in chain]==['FREE1','FREE2']*5
        assert all(x.api_key!='PAID' for x in chain)
        assert all(chain[i].model==chain[i+1].model for i in range(0,10,2))
        if department=='hydraulika':
            assert chain[0].model=='gemini-3.5-flash-lite'
            assert chain[0].label=='Gemini 3.5 Flash Lite (klucz darmowy)'


def test_quantity_chain_single_free_pool_keeps_historical_models_and_order():
    with patch.object(settings,'gemini_api_key_free','FREE1'), \
         patch.object(settings,'gemini_api_key_free_2',None):
        chain=quantity_verification_chain('hydraulika')
        assert len(chain)==5
        assert [step.model for step in chain]==[
            'gemini-3.5-flash-lite','gemini-3-flash-preview',
            'gemini-3.1-flash-lite','gemini-3.5-flash','gemini-3.6-flash']


def test_verification_timeout_flags_uncertain_ones_without_modifying_data_or_matcher():
    rows=[
        {'rozpoznana_nazwa':'Mufa fi 40','ilosc_wydana':1,'ilosc_zuzyta':None,
         'match_kod':'A1','needs_review':False,'form_note':''},
        {'rozpoznana_nazwa':'Kolanko','ilosc_wydana':4,'ilosc_zuzyta':3,
         'match_kod':'B1','needs_review':False,'form_note':''},
    ]
    flagged=flag_unverified_quantities(rows,'hydraulika')
    assert flagged==1 and rows[0]['needs_review'] is True
    assert (rows[0]['ilosc_wydana'],rows[0]['ilosc_zuzyta'],rows[0]['match_kod'])==(1,None,'A1')
    assert rows[1]['needs_review'] is False
    assert flag_unverified_quantities(rows,'hydraulika')==1
    assert rows[0]['form_note'].count('Limit czasu')==1


def test_electric_timeout_flags_only_both_missing():
    rows=[{'ilosc_wydana':1,'ilosc_zuzyta':None,'needs_review':False,'form_note':''},
          {'ilosc_wydana':None,'ilosc_zuzyta':None,'needs_review':False,'form_note':''}]
    assert flag_unverified_quantities(rows,'elektryka')==1
    assert not rows[0]['needs_review'] and rows[1]['needs_review']


def test_adaptive_router_never_reorders_model_families_or_uses_paid():
    cls_result=SimpleNamespace(dzial='hydraulika',confidence=96.,fallback=False,
                               used_provider='AUTO Gemini gemini-3.5-flash-lite darmowy')
    ocr_result=SimpleNamespace(pozycje=[object()],used_provider='FREE2')
    class Metrics:
        def validated_latency_ms(self,label,stage):
            assert stage=='full_ocr_hydraulika'
            if 'gemini-3.6-flash' in label:
                return 2500.0 if label.endswith('FREE2') else 5500.0
            return None
    with patch.object(settings,'gemini_api_key_free','K1'), \
         patch.object(settings,'gemini_api_key_free_2','K2'), \
         patch.object(settings,'gemini_api_key_paid','PAID'), \
         patch.object(classify,'classify_document',new_callable=AsyncMock) as classifier, \
         patch.object(pipeline_hydraulika,'recognize_document_hydraulika',new_callable=AsyncMock) as hyd, \
         patch('app.modules.ocr.image.classification_header_preview',return_value=b'header'), \
         patch.object(Catalog,'from_db',return_value=object()):
        classifier.return_value=cls_result
        hyd.return_value=ocr_result
        _,_,result,_=recognize_gemini_primary([(b'page','image/jpeg')],object(),'Zabrze',
                                              cooldown_store=Metrics())
        steps=hyd.await_args.kwargs['chain']
        assert [s.model for s in steps[:2]]==['gemini-3.5-flash-lite']*2
        assert steps[0].api_key=='K1' and steps[1].api_key=='K2'
        assert [s.model for s in steps[2:4]]==['gemini-3.6-flash']*2
        assert steps[2].api_key=='K2' and steps[3].api_key=='K1'
        assert all(s.api_key!='PAID' for s in steps)
        assert result._matching_catalog_for_jev is not None


def test_redis_latency_estimate_requires_three_samples():
    class FakePipe:
        def __init__(self,redis):self.redis=redis
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def hset(self,key,mapping):self.redis.val[key]=dict(mapping)
        def expire(self,key,ttl):pass
        def execute(self):pass
    class FakeRedis:
        def __init__(self):self.val={}
        def hmget(self,key,*names):
            d=self.val.get(key,{})
            return [d.get(name) for name in names]
        def pipeline(self,transaction=True):return FakePipe(self)
    metrics=RedisOCRCooldownStore(FakeRedis())
    assert metrics.validated_latency_ms('label','full_ocr_hydraulika') is None
    for n in (4000,3000):
        metrics.record_validated_latency('label','full_ocr_hydraulika',n)
        assert metrics.validated_latency_ms('label','full_ocr_hydraulika') is None
    metrics.record_validated_latency('label','full_ocr_hydraulika',2000)
    assert metrics.validated_latency_ms('label','full_ocr_hydraulika')>2000
