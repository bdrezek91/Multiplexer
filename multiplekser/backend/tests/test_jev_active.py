import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.decision import active
from app.modules.matcher import match_against_catalog
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog():
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def _item(query, match):
    return {
        "rozpoznana_nazwa": query,
        "match_kod": match.kod,
        "match_nazwa": match.nazwa,
        "match_jm": match.jm_override,
        "match_quality": match.quality,
        "match_score": match.ratio,
        "matched_product_id": None,
    }
def _result(match, jev_kod):
    return SimpleNamespace(
        matcher_kod=match.kod,
        jev_kod=jev_kod,
        agrees=(match.kod == jev_kod),
        matcher_in_shortlist=True,
        confidence=0.91,
        model="jev-test",
        probabilities={},
        query_features={},
        candidates=[],
        input_tokens=10,
        output_tokens=2,
        duration_ms=123,
    )


@pytest.mark.asyncio
async def test_active_moze_zmienic_niechronione_dopasowanie(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")
    query = "Różnicówka niemiecka 1 fazowa 40A"
    match = match_against_catalog(query, catalog)
    target = next(p for p in catalog.products if p.kod != match.kod)
    items = [_item(query, match)]

    async def fake(**kwargs):
        return _result(match, target.kod)

    monkeypatch.setattr(active, "evaluate_shadow", fake)
    rows = await active.apply_jev_active(
        items=items,
        catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES,
        magazyn=None,
        dzial="elektryka",
        resolve_product_id=lambda kod: "pid",
    )

    assert items[0]["match_kod"] == target.kod
    assert items[0]["matched_product_id"] == "pid"
    assert rows[0]["applied"] is True


@pytest.mark.asyncio
async def test_active_nie_nadpisuje_special_rule(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")
    query = "peszel"
    match = match_against_catalog(query, catalog, special_rules=DEFAULT_SPECIAL_RULES)
    target = next(p for p in catalog.products if p.kod != match.kod)
    items = [_item(query, match)]

    async def fake(**kwargs):
        return _result(match, target.kod)

    monkeypatch.setattr(active, "evaluate_shadow", fake)
    rows = await active.apply_jev_active(
        items=items,
        catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES,
        magazyn=None,
        dzial="elektryka",
        resolve_product_id=lambda kod: "pid",
    )

    assert items[0]["match_kod"] == match.kod
    assert rows[0]["applied"] is False
    assert rows[0]["locked_by_special_rule"] is True


@pytest.mark.asyncio
async def test_active_other_zostawia_matcher(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")
    query = "Różnicówka niemiecka 1 fazowa 40A"
    match = match_against_catalog(query, catalog)
    items = [_item(query, match)]

    async def fake(**kwargs):
        return _result(match, None)

    monkeypatch.setattr(active, "evaluate_shadow", fake)
    rows = await active.apply_jev_active(
        items=items,
        catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES,
        magazyn=None,
        dzial="elektryka",
        resolve_product_id=lambda kod: "pid",
    )

    assert items[0]["match_kod"] == match.kod
    assert rows[0]["applied"] is False
