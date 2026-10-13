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
def test_primary_gemini_only_one_free_model_and_preserves_header(department):
    classified=SimpleNamespace(dzial=department,confidence=94.0,fallback=False)
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
        assert len(chain)==1
        assert chain[0].api_key=="KEY-FREE"
        assert chain[0].api_key!="KEY-PAID"
        assert chain[0].model=="gemini-3.5-flash-lite"
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
        assert cls.await_args.kwargs["chain"][0].api_key=="KEY-FREE"
