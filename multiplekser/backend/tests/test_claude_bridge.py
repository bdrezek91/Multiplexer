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
