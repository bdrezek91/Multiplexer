"""V4 never silently picks unsafe handwritten amounts or drops invalid pages."""
import pytest
from app.modules.documents.auto_v4_quality import normalize_raw_quantities, evaluate_rows


def row(**kw):
    data={"nazwa":"Kolanko fi 20","ilosc_wydana":1,"ilosc_zuzyta":2,
          "ilosc_wydana_raw":"/","ilosc_zuzyta_raw":"2V","ma_oznaczenie":True,"strona":1}
    data.update(kw)
    return data


def test_hydraulic_slash_and_checkmark_preserve_1_and_2():
    v,flags=normalize_raw_quantities(row(),"hydraulika")
    assert (v["ilosc_wydana"],v["ilosc_zuzyta"])==(1,2)
    assert flags==[]


def test_hydraulic_number_vs_checkmark_forces_review_not_1():
    v,flags=normalize_raw_quantities(row(ilosc_wydana_raw="V"),"hydraulika")
    assert v["ilosc_wydana"] is None
    assert "ilosc_wydana:raw_numeric_conflict" in flags
    assert v["ilosc_zuzyta"]==2


def test_hydraulic_dash_must_not_become_1():
    v,flags=normalize_raw_quantities(row(ilosc_wydana_raw="-"),"hydraulika")
    assert v["ilosc_wydana"] is None
    assert flags


def test_hydraulic_incorrect_numeric_inference_is_not_copied():
    v,flags=normalize_raw_quantities(row(ilosc_wydana=4,ilosc_wydana_raw="1"),"hydraulika")
    assert v["ilosc_wydana"] is None and v["ilosc_zuzyta"]==2
    assert "ilosc_wydana:raw_numeric_conflict" in flags


def test_unclear_handwritten_not_automatically_number():
    v,flags=normalize_raw_quantities(row(ilosc_wydana_raw="~~",ilosc_wydana=1),"hydraulika")
    assert v["ilosc_wydana"] is None
    assert "ilosc_wydana:unknown_raw_mark" in flags


def test_invalid_page_fails_closed():
    with pytest.raises(ValueError,match="invalid page"):
        evaluate_rows([row(strona=3)],"hydraulika",2)


def test_all_rows_remain_in_order_with_review_flags():
    r,n=evaluate_rows([row(),row(nazwa="Kolanko fi 25",ilosc_wydana_raw="V")],"hydraulika",1)
    assert [x["nazwa"] for x in r]==["Kolanko fi 20","Kolanko fi 25"]
    assert r[1]["ilosc_wydana"] is None
    assert any("row_2:" in item for item in n)


def test_electrical_numeric_disagreement_flagged_without_qty_guess():
    v,notes=normalize_raw_quantities(row(ilosc_wydana_raw="4",ilosc_wydana=1),"elektryka")
    assert v["ilosc_wydana"] is None
    assert notes


def test_boolean_cannot_become_quantity_one():
    v,notes=normalize_raw_quantities(row(ilosc_wydana=True),"hydraulika")
    assert v["ilosc_wydana"] is None
    assert notes
