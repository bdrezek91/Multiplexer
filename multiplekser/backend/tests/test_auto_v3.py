"""AUTO V3 guardrails without external AI/database calls."""

import pytest

from app.modules.documents.auto_v3 import (
    AmbiguousDepartment,
    classify_auto_dzial,
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
