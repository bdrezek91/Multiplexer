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
async def test_active_nie_nadpisuje_dobrego_matchera(monkeypatch, catalog):
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

    assert items[0]["match_kod"] == match.kod
    assert items[0]["matched_product_id"] is None
    assert rows[0]["applied"] is False


@pytest.mark.asyncio
async def test_active_moze_uratowac_slaby_matcher(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")
    query = "Różnicówka niemiecka 1 fazowa 40A"
    match = match_against_catalog(query, catalog)
    target = next(p for p in catalog.products if p.kod != match.kod)
    items = [_item(query, match)]
    items[0]["match_quality"] = "bad"
    items[0]["match_score"] = 0.10

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
    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
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
    ctx = captured["business_rule_context"]
    assert ctx["authoritative"] is True
    assert ctx["kind"] == "special_rule"
    assert ctx["target_kod"] == match.kod
    assert "peszel" in ctx["description"].lower()


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


def test_konwencja_dampol_brak_3p_oznacza_1p(catalog):
    one_p = catalog.find_by_kod("BEZPIECZNIK 25A NIEMIECKI 1P")
    three_p = catalog.find_by_kod("BEZPIECZNIK 25A NIEMIECKI 3P")
    assert one_p is not None
    assert three_p is not None

    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki", one_p) is True
    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki", three_p) is False
    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki 3P", three_p) is True
    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki 3P", one_p) is False
    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki 3 fazowy", three_p) is True
    assert active._candidate_respects_poles("Wyłącznik nadprądowy 25A niemiecki 3 fazowy", one_p) is False


@pytest.mark.parametrize("query", [
    "Wyłącznik nadprądowy 25A niemiecki 3 fazowy",
    "Bezpiecznik 25A niemiecki 3F",
    "Bezpiecznik 25A niemiecki trójfazowy",
])
def test_25a_niemiecki_jawnie_3_fazowy_zawsze_wybiera_3p(catalog, query):
    for magazyn in ("Zabrze", "Czekanów"):
        match = match_against_catalog(query, catalog, magazyn=magazyn)
        assert match.kod == "BEZPIECZNIK 25A NIEMIECKI 3P"


@pytest.mark.asyncio
async def test_active_nie_pozwala_jev_zmienic_1p_na_3p_bez_3p_na_wydawce(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")

    query = "Wyłącznik nadprądowy 25A niemiecki"
    match = match_against_catalog(query, catalog, magazyn="Czekanów")
    assert match.kod == "BEZPIECZNIK 25A NIEMIECKI 1P"

    target = catalog.find_by_kod("BEZPIECZNIK 25A NIEMIECKI 3P")
    assert target is not None
    items = [_item(query, match)]

    async def fake(**kwargs):
        return _result(match, target.kod)

    monkeypatch.setattr(active, "evaluate_shadow", fake)
    rows = await active.apply_jev_active(
        items=items,
        catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES,
        magazyn="Czekanów",
        dzial="elektryka",
        resolve_product_id=lambda kod: "pid",
    )

    assert items[0]["match_kod"] == "BEZPIECZNIK 25A NIEMIECKI 1P"
    assert rows[0]["applied"] is False
    assert rows[0]["locked_by_warehouse_variant"] is True
    assert rows[0]["query_features"]["active_locked_by_warehouse_variant"] is True


@pytest.mark.asyncio
async def test_active_zabrze_nie_pozwala_jev_dopisac_1p(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")

    query = "Wyłącznik nadprądowy 25A niemiecki"
    match = match_against_catalog(query, catalog, magazyn="Zabrze")
    assert match.kod == "BEZPIECZNIK 25A NIEMIECKI"

    target = catalog.find_by_kod("BEZPIECZNIK 25A NIEMIECKI 1P")
    assert target is not None
    items = [_item(query, match)]
    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return _result(match, target.kod)

    monkeypatch.setattr(active, "evaluate_shadow", fake)
    rows = await active.apply_jev_active(
        items=items,
        catalog=catalog,
        special_rules=DEFAULT_SPECIAL_RULES,
        magazyn="Zabrze",
        dzial="elektryka",
        resolve_product_id=lambda kod: "pid",
    )

    assert items[0]["match_kod"] == "BEZPIECZNIK 25A NIEMIECKI"
    assert rows[0]["applied"] is False
    assert rows[0]["locked_by_warehouse_variant"] is True
    assert captured["business_rule_context"]["kind"] == "warehouse_variant"
    assert captured["business_rule_context"]["target_kod"] == "BEZPIECZNIK 25A NIEMIECKI"


@pytest.mark.asyncio
async def test_active_other_czysci_slaby_matcher_i_wymaga_weryfikacji(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "active")

    query = "wtyk RJ45"
    match = match_against_catalog(query, catalog)
    assert match.quality == "bad"
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

    assert items[0]["match_kod"] is None
    assert items[0]["match_nazwa"] is None
    assert items[0]["matched_product_id"] is None
    assert items[0]["needs_review"] is True
    assert items[0]["match_quality"] == "bad"
    assert "OTHER" in items[0]["form_note"]
    assert rows[0]["applied"] is False
    assert rows[0]["query_features"]["active_cleared_weak_match"] is True
