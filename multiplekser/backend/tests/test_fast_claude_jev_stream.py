"""Fast Claude->JEV streaming bridge unit tests, no external network or DB."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT=Path(__file__).parents[1]/"scripts"/"jev_stream_shadow.py"
if not SCRIPT.is_file():
    SCRIPT=Path("/tmp/jev_stream_shadow.py")
spec=importlib.util.spec_from_file_location("jev_stream_shadow_under_test",SCRIPT)
stream=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stream)


def sample():
    return {"page":2,"rows":[{"nazwa":"Kolanko kanalizacyjne fi 40 45 st",
        "ilosc_wydana":4,"ilosc_zuzyta":1}]}


@pytest.mark.parametrize("qty",[(4,1),(None,1),(2,None)])
def test_jev_stream_preserves_claude_quantities(monkeypatch,qty):
    emitted=[]
    monkeypatch.setattr(stream,"emit",emitted.append)
    monkeypatch.setattr(stream,"match_against_catalog_hydraulika",
        lambda *args,**kwargs:SimpleNamespace(
            kod="KOLANKO KANALIZACYJNE FI 40 45 ST",
            nazwa="Kolanko kanalizacyjne fi 40 45 st",
            jm_override="SZT",quality="ok",ratio=1.0
        ))
    async def fake_jev(**kwargs):
        items=kwargs["items"]
        assert kwargs["dzial"]=="hydraulika"
        assert items[0]["ilosc_wydana"]==qty[0]
        assert items[0]["ilosc_zuzyta"]==qty[1]
        return [{"sequence":0,"jev_kod":"KOLANKO KANALIZACYJNE FI 40 45 ST",
                 "applied":False}]
    monkeypatch.setattr(stream,"apply_jev_active",fake_jev)
    entry=sample()
    entry["rows"][0]["ilosc_wydana"]=qty[0]
    entry["rows"][0]["ilosc_zuzyta"]=qty[1]
    stream.page_decisions(entry,object(),[],"hydraulika",None)
    result=emitted[0]
    assert result["kind"]=="result"
    assert result["count"]==1
    assert result["jev_responses"]==1
    assert result["qty_unchanged"] is True
    assert result["rows"][0]["w"]==qty[0]
    assert result["rows"][0]["z"]==qty[1]


def test_jev_stream_detects_illegal_quantity_mutation(monkeypatch):
    monkeypatch.setattr(stream,"emit",lambda _x:None)
    monkeypatch.setattr(stream,"match_against_catalog_hydraulika",
        lambda *args,**kwargs:SimpleNamespace(
            kod="TEST",nazwa="Test",jm_override="SZT",quality="ok",ratio=1.0
        ))
    async def bad_jev(**kwargs):
        kwargs["items"][0]["ilosc_zuzyta"]=555
        return []
    monkeypatch.setattr(stream,"apply_jev_active",bad_jev)
    with pytest.raises(AssertionError):
        stream.page_decisions(sample(),object(),[],"hydraulika",None)
