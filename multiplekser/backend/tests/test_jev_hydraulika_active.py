"""Hydraulika JEV active: twarde zabezpieczenia przy zmianie kodu Optimy."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.decision import active
from app.modules.matcher import match_against_catalog_hydraulika
from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA
from app.modules.products import Catalog

FIXTURE=Path(__file__).parent/"fixtures"/"baza_hydraulika.json"


@pytest.fixture(scope="module")
def catalog():
    return Catalog.from_json_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))


def base_item(query, match):
    return dict(rozpoznana_nazwa=query, match_kod=match.kod,
                match_nazwa=match.nazwa, match_jm=match.jm_override,
                match_quality=match.quality, match_score=match.ratio,
                matched_product_id=None, needs_review=False, form_note="")


def answer(match, code):
    return SimpleNamespace(
        matcher_kod=match.kod, jev_kod=code, agrees=match.kod==code,
        matcher_in_shortlist=True, confidence=0.93, model="jev-mock",
        probabilities={}, query_features={}, candidates=[],
        input_tokens=12, output_tokens=2, duration_ms=10,
    )


async def run_active(monkeypatch, catalog, query, *, target, weaken=False,
                     error=False, result_none=False):
    monkeypatch.setenv("JEV_ENABLED","true")
    monkeypatch.setenv("JEV_MODE","active")
    match=match_against_catalog_hydraulika(query,catalog)
    item=base_item(query,match)
    if weaken:
        item["match_quality"]="bad"
        item["match_score"]=0.1
    async def fake(**kwargs):
        if error:raise RuntimeError("typesafe timeout")
        if result_none:return None
        return answer(match,target)
    monkeypatch.setattr(active,"evaluate_shadow",fake)
    rows=await active.apply_jev_active(
        items=[item], catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES_HYDRAULIKA,
        magazyn=None, dzial="hydraulika",
        resolve_product_id=lambda kod: "id-for:"+str(kod),
    )
    return item,rows,match


@pytest.mark.asyncio
async def test_hydraulika_jev_nie_nadpisuje_dobrego_matchera(monkeypatch,catalog):
    query="Kolanko kanalizacyjne fi 40 45 st"
    item,rows,match=await run_active(
        monkeypatch,catalog,query,target="KOLANKO KANALIZACYJNE FI 40 90 ST")
    assert item["match_kod"]==match.kod
    assert rows[0]["applied"] is False


@pytest.mark.asyncio
async def test_hydraulika_jev_poprawia_slaby_matcher(monkeypatch,catalog):
    query="Kolanko kanalizacyjne fi 40 45 st"
    target="KOLANKO KANALIZACYJNE FI 40 45 ST"
    item,rows,match=await run_active(
        monkeypatch,catalog,query,target=target,weaken=True)
    assert item["match_kod"]==target
    assert item["match_quality"]=="ok"
    assert item["matched_product_id"]=="id-for:"+target
    assert rows[0]["query_features"]["active_rejected_by_hydraulika_attrs"] is False


@pytest.mark.asyncio
async def test_hydraulika_jev_nie_moze_zmienic_kata_45_na_90(monkeypatch,catalog):
    query="Kolanko kanalizacyjne fi 40 45 st"
    item,rows,match=await run_active(
        monkeypatch,catalog,query,target="KOLANKO KANALIZACYJNE FI 40 90 ST",
        weaken=True)
    assert item["match_kod"]==match.kod
    assert rows[0]["applied"] is False
    assert rows[0]["query_features"]["active_rejected_by_hydraulika_attrs"] is True


@pytest.mark.parametrize("query,bad_code",[
    ("Kolanko kanalizacyjne fi 40 45 st", "KOLANKO KANALIZACYJNE FI 40 90 ST"),
    ("Kolanko kanalizacyjne fi 40 90 st", "KOLANKO KANALIZACYJNE FI 40 45 ST"),
    ("Blat kuchenny 1250x600","BLAT KUCHENNY 1200X600"),
])
def test_hydraulika_jawny_konflikt_cech_jest_blokowany(catalog,query,bad_code):
    candidate=catalog.find_by_kod(bad_code)
    assert candidate is not None
    assert active._candidate_respects_hydraulika_features(query,candidate) is False


@pytest.mark.asyncio
async def test_hydraulika_zaslepka_ma_wyzszy_priorytet_niz_jev(monkeypatch,catalog):
    query="Zaślepka czarna"
    item,rows,match=await run_active(
        monkeypatch,catalog,query,target="KOLANKO KANALIZACYJNE FI 40 45 ST",
        weaken=True)
    assert item["match_kod"]==match.kod
    assert rows[0]["locked_by_special_rule"] is True
    assert rows[0]["applied"] is False


@pytest.mark.asyncio
async def test_hydraulika_fail_open_gdy_jev_niedostepny(monkeypatch,catalog):
    query="Kolanko kanalizacyjne fi 40 45 st"
    item,rows,match=await run_active(
        monkeypatch,catalog,query,target=None,weaken=True,error=True)
    assert item["match_kod"]==match.kod
    assert rows==[]


@pytest.mark.asyncio
async def test_hydraulika_other_slaby_matcher_do_weryfikacji(monkeypatch,catalog):
    query="Kolanko kanalizacyjne fi 40 45 st"
    item,rows,_match=await run_active(
        monkeypatch,catalog,query,target=None,weaken=True)
    assert item["match_kod"] is None
    assert item["needs_review"] is True
    assert rows[0]["query_features"]["active_cleared_weak_match"] is True
