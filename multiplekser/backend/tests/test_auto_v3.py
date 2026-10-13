"""AUTO V3 guardrails without external AI/database calls."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.documents.auto_v3 import (
    AmbiguousDepartment,
    classify_auto_dzial,
    reconcile_verify_rows,
    recognize_with_free_gemini,
)


def row(name, hint=None, w=1, z=1, page=1):
    return {"nazwa":name,"_dzial_hint":hint,"ilosc_wydana":str(w),
            "ilosc_zuzyta":str(z),"page_number":page}


def test_header_hydraulika_with_confirming_materials():
    rows=[row("Kolanko kanalizacyjne fi 40 45 st","hydraulika"),
          row("Rura fi 32 30 cm"),row("Trójnik PP 20")]
    department,confidence,_=classify_auto_dzial(rows)
    assert department=="hydraulika" and confidence>=90


def test_header_elektryka_with_confirming_materials():
    rows=[row("Gniazdo natynkowe Schuko","elektryka"),
          row("Wyłącznik nadprądowy 25A"),row("Przewód 3x2,5")]
    department,confidence,_=classify_auto_dzial(rows)
    assert department=="elektryka" and confidence>=90


def test_no_header_can_classify_clear_document():
    rows=[row("Kolanko kanalizacyjne fi 40 45 st"),
          row("Rura fi 32 30 cm"),row("Trójnik PP 20")]
    assert classify_auto_dzial(rows)[0]=="hydraulika"


def test_no_header_ambiguous_fails_safely():
    with pytest.raises(AmbiguousDepartment):
        classify_auto_dzial([row("Blat drewniany"),row("Zaslepka")])


def test_conflicting_header_and_names_cannot_silently_choose_catalog():
    with pytest.raises(AmbiguousDepartment):
        classify_auto_dzial([row("Kolanko fi 40","elektryka"),
                             row("Rura fi 32","elektryka"),
                             row("Kompakt WC","elektryka"),
                             row("Trójnik kanalizacyjny","elektryka")])


def position():
    return SimpleNamespace(needs_review=True,form_note="",off_form=False,
                           match=SimpleNamespace(quality="exact"))


def test_opus_agrees_on_both_columns_and_verifies():
    p=position()
    confirmed,conflicts=reconcile_verify_rows(
        [(row("Trójnik PP 20",w=4,z=5),p)],
        [row("Trójnik PP 20",w=4,z=5)]
    )
    assert (confirmed,conflicts)==(1,0)
    assert not p.needs_review
    assert "potwierdził" in p.form_note


def test_opus_quantity_disagrees_and_never_changes_original():
    p=position()
    original=row("Trójnik PP 20",w=4,z=5)
    confirmed,conflicts=reconcile_verify_rows(
        [(original,p)],[row("Trójnik PP 20",w=4,z=4)]
    )
    assert (confirmed,conflicts)==(0,1)
    assert p.needs_review
    assert original["ilosc_zuzyta"]=="5"
    assert "Sprawdź skan" in p.form_note


def test_opus_missing_row_must_not_be_accepted():
    p=position()
    assert reconcile_verify_rows([(row("Trójnik PP 20"),p)],[])[1]==1
    assert p.needs_review


def test_free_fallback_does_not_start_if_free_key_unavailable():
    from app.core.config import settings
    with patch.object(settings,"gemini_api_key_free",None):
        with pytest.raises(RuntimeError,match="darmowego"):
            recognize_with_free_gemini([(b"x","image/jpeg")],object(),None)


def test_free_fallback_filters_out_all_paid_providers():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.core.config import settings
    from app.modules.ocr import chain, classify, pipeline_hydraulika, image
    from app.modules.products import Catalog

    free = SimpleNamespace(label="Gemini klucz darmowy", api_key="ONLY-FREE")
    paid = SimpleNamespace(label="Gemini klucz platny", api_key="PAID-KEY")
    with patch.object(settings, "gemini_api_key_free", "ONLY-FREE"), \
         patch.object(chain, "classify_ocr_chain", return_value=[free, paid]), \
         patch.object(chain, "background_verification_chain", return_value=[free, paid]), \
         patch.object(image, "classification_header_preview", return_value=b"header"), \
         patch.object(classify, "classify_document", new_callable=AsyncMock) as classify_mock, \
         patch.object(pipeline_hydraulika, "recognize_document_hydraulika", new_callable=AsyncMock) as ocr_mock, \
         patch.object(Catalog, "from_db", return_value=object()):
        classify_mock.return_value=SimpleNamespace(dzial="hydraulika",confidence=94,fallback=False)
        ocr_mock.return_value=SimpleNamespace(used_provider="Gemini",pozycje=[])
        c,department,output=recognize_with_free_gemini(
            [(b"image","image/jpeg")], object(), "Zabrze"
        )
        assert department=="hydraulika"
        assert classify_mock.await_args.kwargs["chain"]==[free]
        assert ocr_mock.await_args.kwargs["chain"]==[free]
        assert "darmowy Gemini" in output.used_provider
