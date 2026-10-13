"""Claude + independent FREE Gemini audit, only matcher/JEV may choose catalog code."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.documents.auto_gemini_audit import (
    AUDIT_PROMPT, FREE_MODEL, GeminiAudit, _quantity,
    compare_gemini_to_claude, read_free_gemini_audit,
)


def test_gemini_audit_never_uses_paid_api_key_or_paid_model():
    from app.core.config import settings
    from app.modules.ocr.providers import GeminiProvider

    response='{"dzial":"hydraulika","numer_projektu":"126/07","pracownik":"Dawid","pozycje":['              '{"strona":1,"nazwa":"Kolanko PP 20","ilosc_wydana":2,"ilosc_zuzyta":1}]}'
    with patch.object(settings, "gemini_api_key_free", "FREE-ONLY"), \
         patch.object(settings, "gemini_api_key_paid", "PAID-NEVER"), \
         patch.object(GeminiProvider, "recognize", new_callable=AsyncMock) as mocked:
        mocked.return_value=response
        outcome=read_free_gemini_audit([(b"example","image/jpeg")])
        call=mocked.await_args.kwargs
        assert call["api_key"]=="FREE-ONLY"
        assert call["api_key"]!="PAID-NEVER"
        assert call["model"]==FREE_MODEL
        assert call["thinking_level"]=="low"
        assert len(outcome.rows)==1
        assert outcome.project=="126/07"
        assert outcome.employee=="Dawid"
        assert outcome.department=="hydraulika"
        assert "NIE SZUKAJ numeru plomby" in AUDIT_PROMPT


def test_gemini_audit_requires_free_key():
    from app.core.config import settings
    with patch.object(settings, "gemini_api_key_free", None):
        with pytest.raises(RuntimeError,match="darmowego"):
            read_free_gemini_audit([(b"image","image/jpeg")])


def position():
    return SimpleNamespace(needs_review=False, form_note="", match=SimpleNamespace(kod="UNCHANGED"))


def audit(rows):
    return GeminiAudit(rows=rows,department="hydraulika",project=None,employee=None,
                       seconds=2.1,model=FREE_MODEL)


def test_matching_quantities_do_not_change_codes_or_need_review():
    first=[{"nazwa":"Kolanko PP fi 20","page_number":1,
            "ilosc_wydana":"4","ilosc_zuzyta":"5"}]
    second=[{"nazwa":"Kolanko PP fi 20","page_number":1,
             "ilosc_wydana":4.0,"ilosc_zuzyta":5.0}]
    p=position()
    metrics=compare_gemini_to_claude(first,[p],audit(second))
    assert metrics["agreed"]==1 and metrics["conflicts"]==0
    assert not p.needs_review
    assert p.match.kod=="UNCHANGED"
    assert first[0]["ilosc_zuzyta"]=="5"


def test_quantity_disagreement_flags_review_not_auto_overwrite():
    first=[{"nazwa":"Rura fi 32 30 cm","page_number":2,
            "ilosc_wydana":"2","ilosc_zuzyta":"1"}]
    second=[{"nazwa":"Rura fi 32 30 cm","page_number":2,
             "ilosc_wydana":2.0,"ilosc_zuzyta":2.0}]
    p=position()
    metrics=compare_gemini_to_claude(first,[p],audit(second))
    assert metrics["conflicts"]==1
    assert p.needs_review and first[0]["_uncertain"]
    assert "Claude" in p.form_note and "Gemini" in p.form_note
    assert first[0]["ilosc_zuzyta"]=="1"
    assert p.match.kod=="UNCHANGED"


def test_only_gemini_rows_reported_as_possible_claude_omission():
    first=[{"nazwa":"Rura fi 32","page_number":1,
            "ilosc_wydana":"2","ilosc_zuzyta":"2"}]
    second=[
        {"nazwa":"Rura fi 32","page_number":1,"ilosc_wydana":2.0,"ilosc_zuzyta":2.0},
        {"nazwa":"Trójnik PP","page_number":1,"ilosc_wydana":4.0,"ilosc_zuzyta":1.0}
    ]
    result=compare_gemini_to_claude(first,[position()],audit(second))
    assert result["gemini_only"]==1
    assert result["gemini_only_examples"]==["Trójnik PP"]


def test_uncertain_duplicates_do_not_assign_other_rows_quantities():
    first=[
        {"nazwa":"Kolanko PP","page_number":1,"ilosc_wydana":"4","ilosc_zuzyta":"1"},
        {"nazwa":"Kolanko PP","page_number":1,"ilosc_wydana":"5","ilosc_zuzyta":"1"},
    ]
    second=[{"nazwa":"Kolanko PP","page_number":1,"ilosc_wydana":4.0,"ilosc_zuzyta":1.0}]
    positions=[position(),position()]
    result=compare_gemini_to_claude(first,positions,audit(second))
    assert result["claude_only"]==1
    assert positions[1].needs_review
    assert first[1]["ilosc_wydana"]=="5"


@pytest.mark.parametrize("value,expected", [
    ("1",1.0),("1,5",1.5),("4",4.0),(None,None),
    (True,None),("nieczytelne",None),(-1,None),("4 szt",None),
])
def test_no_assumed_quantities(value,expected):
    assert _quantity(value)==expected


def test_header_model_disagreement_does_not_change_source():
    from app.modules.documents.auto_gemini_audit import header_gemini_disagreements
    primary={"numer_projektu":"126/07","pracownik":"Dawid"}
    audit=GeminiAudit(rows=[],department="hydraulika",project="127/07",
                      employee="Dawid",seconds=1.0,model=FREE_MODEL)
    differences=header_gemini_disagreements(primary,audit)
    assert len(differences)==1 and "numer projektu" in differences[0]
    assert primary["numer_projektu"]=="126/07"
    same=GeminiAudit(rows=[],department="hydraulika",project="126/07",
                     employee="Dawid",seconds=1.0,model=FREE_MODEL)
    assert header_gemini_disagreements(primary,same)==[]
