"""
Testy regresyjne Matchera dla Hydrauliki - analogicznie do test_matcher.py (Elektryka).
Kazdy przypadek to realna, zidentyfikowana wczesniej kolizja/ryzyko z analizy katalogu
(patrz docs/MIGRATION_PLAN_HYDRAULIKA.md, sekcja 2), nie test syntetyczny.
"""
import json
from pathlib import Path

import pytest

from app.modules.matcher import match_against_catalog_hydraulika
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_hydraulika.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db, dzial="hydraulika")


def test_zawor_katowy_gwinty_rozroznione(catalog):
    """Ryzyko z analizy: 3 warianty ZAWÓR KĄTOWY rozniace sie WYLACZNIE gwintem -
    bez atrybutu gwint_cal, samo dopasowanie tekstowe by je myliło."""
    r1 = match_against_catalog_hydraulika("Zawór kątowy 1/2x3/4", catalog)
    r2 = match_against_catalog_hydraulika("Zawór kątowy 1/2x1/2", catalog)
    r3 = match_against_catalog_hydraulika("Zawór kątowy 1/2x3/8", catalog)
    assert r1.kod == "ZAWÓR KĄTOWY 1/2X3/4"
    assert r2.kod == "ZAWÓR KĄTOWY 1/2X1/2"
    assert r3.kod == "ZAWÓR KĄTOWY 1/2X3/8"
    assert len({r1.kod, r2.kod, r3.kod}) == 3


def test_kolanka_kanalizacyjne_srednica_i_kat(catalog):
    """Rodzina 'Kolanko kanalizacyjne FI {32,40,50} {15,30,45,67,90} ST' - 20 wariantow
    roznych TYLKO srednica+katem - test na losowej probce z tej rodziny."""
    r = match_against_catalog_hydraulika("Kolanko kanalizacyjne fi 40 45 st", catalog)
    assert r.kod == "KOLANKO KANALIZACYJNE FI 40 45 ST"
    assert r.quality == "ok"


def test_material_pex_odrozniany(catalog):
    """Łącznik kolankowy GW vs GZ (ten sam gwint/material, rozne zlacze)."""
    r_gw = match_against_catalog_hydraulika("Łącznik kolankowy GW 16x1/2 PEX", catalog)
    r_gz = match_against_catalog_hydraulika("Łącznik kolankowy GZ 16x1/2 PEX", catalog)
    assert r_gw.kod != r_gz.kod
    assert "GW" in r_gw.kod
    assert "GZ" in r_gz.kod


def test_waz_gwint_i_dlugosc(catalog):
    """WĄŻ 1/2X3/8 CALA 40 CM vs 3/8X3/8 CALA 40 CM - rozne gwinty, ta sama dlugosc."""
    r = match_against_catalog_hydraulika("Wąż 1/2x3/8 cala 40 cm", catalog)
    assert r.kod == "WĄŻ 1/2X3/8 CALA 40 CM"


def test_bojler_pojemnosc(catalog):
    r50 = match_against_catalog_hydraulika("Bojler 50 L", catalog)
    r80 = match_against_catalog_hydraulika("Bojler 80 L", catalog)
    assert r50.kod != r80.kod


def test_grzejnik_moc_nie_myli_sie_z_grzejnikiem_lazienkowym(catalog):
    """Ryzyko z analizy: 'grzejnik' to trzy rozne rodziny produktow - moc_W nie jest
    ekstrahowana jako atrybut (parser Hydrauliki jej nie zna), ale zostaje w tekscie
    `core`, wiec Dice coefficient i tak je rozroznia."""
    r = match_against_catalog_hydraulika("Grzejnik 1000W", catalog)
    assert r.kod == "GRZEJNIK 1000W"
    r2 = match_against_catalog_hydraulika("Grzejnik łazienkowy 40x70 biały", catalog)
    assert r2.kod == "GRZEJNIK ŁAZIENKOWY 40X70 BIAŁY"
    assert r.kod != r2.kod


def test_full_catalog_smoke(catalog):
    """Smoke test na calym katalogu (kody jako wlasne zapytania - najlatwiejszy przypadek,
    powinien dawac wysoki odsetek 'ok') - punkt odniesienia do przyszlych poprawek."""
    counts = {"ok": 0, "warn": 0, "bad": 0, "excluded": 0}
    db = json.loads((FIXTURES / "baza_hydraulika.json").read_text(encoding="utf-8"))
    for rec in db["generyczne"].values():
        r = match_against_catalog_hydraulika(rec["nazwa"], catalog)
        counts[r.quality] += 1
    assert counts["ok"] >= 200  # z 247 generycznych
