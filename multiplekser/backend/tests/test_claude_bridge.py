"""Test of optional Claude Pro bridge input validation and file transport."""
from __future__ import annotations
import json
import threading
import time

import pytest

from app.modules.documents import claude_bridge as bridge


def result_with_rows(rows, count=1):
    return {"pages":[{"index":i,"rows":rows} for i in range(1,count+1)]}


def test_validate_ocr_retains_names_and_two_qty_columns():
    rows=bridge.validate_ocr(result_with_rows([
        {"nazwa":"Trójnik PP 20","ilosc_wydana":4,"ilosc_zuzyta":5},
        {"nazwa":"Rura fi 32 30 cm","ilosc_wydana":"2","ilosc_zuzyta":"1"},
    ]),1)
    assert rows[0]["nazwa"]=="Trójnik PP 20"
    assert rows[0]["ilosc_wydana"]=="4"
    assert rows[0]["ilosc_zuzyta"]=="5"
    assert rows[1]["ilosc_zuzyta"]=="1"


@pytest.mark.parametrize("bad", ["2/1","1x",False,-1,0,1000000])
def test_validate_ocr_rejects_bad_quantities(bad):
    with pytest.raises(bridge.ClaudeBridgeError):
        bridge.validate_ocr(result_with_rows([{
            "nazwa":"Trójnik PP 20","ilosc_wydana":bad,"ilosc_zuzyta":1,
        }]),1)


def test_validate_ocr_rejects_missing_pages():
    with pytest.raises(bridge.ClaudeBridgeError,match="wszystkich stron"):
        bridge.validate_ocr(result_with_rows([],0),2)


def test_bridge_uses_private_job_and_cleans_up(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"BRIDGE_ROOT",tmp_path)
    completed={}
    def daemon():
        end=time.monotonic()+4
        while time.monotonic()<end:
            folders=list((tmp_path/"jobs").glob("*/request.json"))
            if folders:
                req=folders[0]
                job=req.parent
                request=json.loads(req.read_text())
                completed["request"]=request
                assert (job/"page1.jpg").read_bytes()==b"FAKE_JPEG"
                (job/"result.json").write_text(json.dumps(result_with_rows([
                    {"nazwa":"Kompakt WC","ilosc_wydana":1,"ilosc_zuzyta":1}
                ])))
                return
            time.sleep(.02)
    t=threading.Thread(target=daemon)
    t.start()
    rows,elapsed=bridge.run_claude_host_bridge("doc-test",[(b"FAKE_JPEG","image/jpeg")],
                                              "hydraulika",timeout_seconds=4)
    t.join(timeout=2)
    assert rows[0]["ilosc_wydana"]=="1"
    assert completed["request"]["dzial"]=="hydraulika"
    assert 0 <= elapsed < 4
    assert list((tmp_path/"jobs").iterdir())==[]


def test_bridge_unavailable_times_out_cleanly(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"BRIDGE_ROOT",tmp_path)
    with pytest.raises(bridge.ClaudeBridgeError,match="nie odpowiedział"):
        bridge.run_claude_host_bridge("doc-test",[(b"FAKE","image/jpeg")],
                                      "elektryka",timeout_seconds=.03)
    assert list((tmp_path/"jobs").iterdir())==[]


def test_header_from_claude_keeps_all_existing_gemini_fields():
    """Parity contract: neither AUTO nor Claude can drop header metadata."""
    response={
        "pages":[{
            "index":1,
            "rows":[{"nazwa":"Kolanko PP 20","ilosc_wydana":2,"ilosc_zuzyta":1}],
            "dzial_hint":"hydraulika",
            "header":{
                "numer_projektu":"625/05/26",
                "pracownik":"Jan Kowalski",
                "numer_plomby":"P-109",
            },
        }],
    }
    meta=bridge.extract_document_header(response)
    assert meta=={
        "numer_projektu":"625/05/2026",
        "pracownik":"Jan Kowalski",
        "numer_plomby":"P-109",
    }
    assert bridge.validate_ocr(response,1)[0]["_dzial_hint"]=="hydraulika"


@pytest.mark.parametrize("raw", ["unknown","-", "Numer Projektu","35/XX/26","35/06/2X"])
def test_header_never_guesses_wrong_project_number(raw):
    meta=bridge.extract_document_header({
        "pages":[{"index":1,"header":{"numer_projektu":raw,"pracownik":"-", "numer_plomby":None}}]
    })
    assert meta["numer_projektu"] is None
    assert meta["pracownik"] is None
    assert meta["numer_plomby"] is None


def test_header_does_not_depend_on_first_page_having_material_rows():
    response={"pages":[
        {"index":1, "rows":[], "header":{
            "numer_projektu":"79/03/2026","pracownik":"Pracownik A", "numer_plomby":"14",
        }},
        {"index":2,"rows":[{"nazwa":"Kolanko","ilosc_wydana":1,"ilosc_zuzyta":1}]},
    ]}
    assert bridge.extract_document_header(response)["numer_projektu"]=="79/03/2026"
    assert len(bridge.validate_ocr(response,2))==1


def test_private_bridge_return_header_without_breaking_old_caller(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"BRIDGE_ROOT",tmp_path)
    def daemon():
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            paths=list((tmp_path/"jobs").glob("*/request.json"))
            if paths:
                path=paths[0].parent/"result.json"
                payload={"pages":[{
                    "index":1,
                    "rows":[{"nazwa":"Przewód","ilosc_wydana":3,"ilosc_zuzyta":2}],
                    "header":{"numer_projektu":"35/06/26","pracownik":"Adam", "numer_plomby":"120"},
                }]}
                path.write_text(json.dumps(payload))
                return
            time.sleep(.01)
    thread=threading.Thread(target=daemon)
    thread.start()
    rows, elapsed, header = bridge.run_claude_host_bridge(
        "doc",[(b"FAKE_JPEG","image/jpeg")],"auto",timeout_seconds=5,
        include_header=True,
    )
    thread.join(timeout=3)
    assert len(rows)==1
    assert elapsed>=0
    assert header["numer_projektu"]=="35/06/2026"
    assert header["pracownik"]=="Adam"
    assert header["numer_plomby"]=="120"


def test_abbreviated_project_is_preserved_exactly():
    source={"pages":[{"index":1, "header":{
        "numer_projektu":"127/07","pracownik":None,"numer_plomby":None,
    }}]}
    header=bridge.extract_document_header(source)
    assert header["numer_projektu"]=="127/07"
    assert header["pracownik"] is None


def test_later_page_can_supply_missing_header_fields():
    source={"pages":[
        {"index":1, "rows":[], "header":{
            "numer_projektu":None,"pracownik":"Anna Nowak","numer_plomby":None,
        }},
        {"index":2, "rows":[], "header":{
            "numer_projektu":"625/05/26","pracownik":None,"numer_plomby":"123",
        }},
    ]}
    assert bridge.extract_document_header(source)=={
        "numer_projektu":"625/05/2026",
        "pracownik":"Anna Nowak",
        "numer_plomby":"123",
    }


def test_conflicting_project_numbers_fail_closed():
    source={"pages":[
        {"index":1,"header":{"numer_projektu":"625/05/26","pracownik":"Jan Nowak"}},
        {"index":2,"header":{"numer_projektu":"626/05/26","pracownik":"Jan Nowak"}},
    ]}
    header=bridge.extract_document_header(source)
    assert header["numer_projektu"] is None
    assert header["pracownik"]=="Jan Nowak"


def test_equivalent_year_formats_are_not_a_conflict():
    source={"pages":[
        {"index":1,"header":{"numer_projektu":"625/05/26"}},
        {"index":2,"header":{"numer_projektu":"625/05/2026"}},
    ]}
    assert bridge.extract_document_header(source)["numer_projektu"]=="625/05/2026"
