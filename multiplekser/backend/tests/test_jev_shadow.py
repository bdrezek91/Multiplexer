"""Testy Jev Shadow (Etap 3/4/5 integracji TypeSafe, 2026-09-29). HTTP zamockowany - zero
prawdziwych wywolan do TypeSafe. Sprawdzaja: shortlista nie zawiera przypadkowych produktow,
diagnostyka trafia do payloadu, matcher_kod nigdy nie jest ujawniany Jev przed odpowiedzia,
i - najwazniejsze - KAZDY blad komunikacji jest fail-open (nie wysadza wywolujacego)."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.modules.decision.jev_shadow import build_shortlist, evaluate_shadow
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def _fake_response(status_code=200, json_data=None):
    kwargs = {"request": httpx.Request("POST", "https://api.typesafe.ai/v1/systemone")}
    if json_data is not None:
        kwargs["json"] = json_data
    return httpx.Response(status_code, **kwargs)


def _jev_ok_response(choice: str, confidence: float = 0.9):
    return _fake_response(json_data={
        "model": "jev-1.13.0",
        "answers": {
            "produkt": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {choice: confidence},
            }
        },
        "usage": {"input_tokens": 10, "output_tokens": 5},
    })


def test_build_shortlist_dla_roznicowki_nie_zawiera_przypadkowych_produktow(catalog):
    """Shortlista dla zapytania o roznicowke nie moze zawierac np. wtyczki - tylko produkty
    z tej samej grupy lub trafione aliasem."""
    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    candidates = build_shortlist(
        query_name="Różnicówka niemiecka 1 fazowa 40A",
        catalog=catalog,
        current_match=match,
        dzial="elektryka",
    )

    assert len(candidates) > 0
    for c in candidates:
        assert "wtyczka" not in c.nazwa.lower()
        assert "różnicówka" in c.nazwa.lower() or "wyłącznik różnicowo" in c.nazwa.lower()


def test_build_shortlist_dolacza_diagnostyke_per_kandydat(catalog):
    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    candidates = build_shortlist(
        query_name="Różnicówka niemiecka 1 fazowa 40A",
        catalog=catalog,
        current_match=match,
        dzial="elektryka",
    )

    assert all(c.diagnostics is not None for c in candidates)
    assert all("country_match" in c.diagnostics for c in candidates)


@pytest.mark.parametrize("env", [{"JEV_ENABLED": "false"}])
def test_evaluate_shadow_wylaczony_zwraca_none(monkeypatch, catalog, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )
    )
    assert result is None


async def test_evaluate_shadow_fail_open_na_blad_http(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    fake = _fake_response(status_code=503, json_data={"error": "unavailable"})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        result = await evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )

    assert result is None  # fail-open - nigdy wyjatku


async def test_evaluate_shadow_fail_open_na_wyjatek_sieciowy(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))):
        result = await evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )

    assert result is None


async def test_evaluate_shadow_nie_ujawnia_matcher_kod_przed_odpowiedzia(monkeypatch, catalog):
    """Krytyczne dla wiarygodnosci testu (V1 byl niewiarygodny, bo Jev znal wybor matchera) -
    sprawdzamy, ze current_match.kod nie pojawia sie ani w state, ani w instructions wyslanych
    do TypeSafe (moze pojawic sie w criteria TYLKO jako opis jednego z wielu kandydatow,
    rownorzednie z pozostalymi - nie jako wskazowka ktory jest 'poprawny')."""
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)
    assert match.kod == "RÓŻNICÓWKA NIEMIECKA CDS240D"

    captured_payload = {}

    async def fake_post(self, url, headers=None, json=None, **kwargs):
        captured_payload.update(json)
        return _jev_ok_response("C0")

    with patch("httpx.AsyncClient.post", new=fake_post):
        await evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )

    instructions = captured_payload["questions"]["produkt"]["instructions"]
    assert "CDS240D" not in instructions
    assert "current_match" not in json.dumps(captured_payload)


async def test_evaluate_shadow_agrees_gdy_jev_wybiera_to_samo_co_matcher(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    candidates = build_shortlist(
        query_name="Różnicówka niemiecka 1 fazowa 40A",
        catalog=catalog, current_match=match, dzial="elektryka",
    )
    matcher_candidate = next(c for c in candidates if c.current_match)

    fake = _jev_ok_response(matcher_candidate.key)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        result = await evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )

    assert result is not None
    assert result.jev_kod == match.kod
    assert result.agrees is True


async def test_evaluate_shadow_other_nie_wymusza_matcher_kod(monkeypatch, catalog):
    monkeypatch.setenv("JEV_ENABLED", "true")
    monkeypatch.setenv("JEV_MODE", "shadow")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    match = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    fake = _jev_ok_response("OTHER", confidence=0.38)
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake)):
        result = await evaluate_shadow(
            query_name="Różnicówka niemiecka 1 fazowa 40A",
            catalog=catalog, current_match=match, dzial="elektryka",
        )

    assert result is not None
    assert result.jev_kod is None
    assert result.agrees is False
    assert result.matcher_kod == match.kod  # matcher wciaz ma swoj wynik, niezmieniony
