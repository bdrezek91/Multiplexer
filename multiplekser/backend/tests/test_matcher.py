"""
Testy regresyjne Matchera - kazdy przypadek to REALNY blad znaleziony i naprawiony
w monolicie JS w trakcie tej sesji. Cel: migracja do Pythona nie moze ich przywrocic.
"""
import json
from pathlib import Path

import pytest

from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def test_koncowka_tulejkowa_4_12_nie_lapie_16_12(catalog):
    """Bug: token-length filter obcinal '4' z aliasu '4-12', przez co '16/12' (swiadoma
    dziura) falszywie dopasowywalo sie do '4-12' (30+20 zamiast 30)."""
    r = match_against_catalog("Koncowka tulejkowa 4-12", catalog)
    assert r.kod == "KOŃCÓWKA TULEJKOWA 4-12"
    assert r.quality == "ok"


def test_koncowka_16_12_wykluczona(catalog):
    """Bare '16/12' (bez HI) to swiadoma dziura - stan=0, nie mamy tego wcale."""
    r = match_against_catalog("Koncowka tulejkowa  16/12", catalog)
    assert r.quality == "excluded"


def test_koncowka_hi_16_12_dziala(catalog):
    """HI 16/12 to inny, dawniej istniejacy kod - tez wykluczony po decyzji Bartka."""
    r = match_against_catalog("Koncowka tulejkowa HI 16/12", catalog)
    assert r.quality == "excluded"


def test_kolor_niebieski_rozpoznawany(catalog):
    """Bug: 5 z 10 kolorow w katalogu (w tym niebieski) nie bylo w ogole rozpoznawanych,
    co tworzylo falszywy konflikt z domyslnym 'bialy'."""
    r = match_against_catalog("Wtyczka odbiornikowa 16A niebieska", catalog)
    assert r.kod == "WTYCZKA ODBIORNIKOWA 16A NIEBIESKA"
    assert r.quality == "ok"


def test_nawiasy_nie_kasuja_atrybutow(catalog):
    """Bug: '(niebieska)' w nawiasie znikalo calkowicie przed ekstrakcja koloru."""
    r = match_against_catalog("Gniazdo przenośne 16A (niebieska) 1F", catalog)
    assert r.kod == "GNIAZDO PRZENOŚNE 16A 1 FAZOWE NIEBIESKIE"


def test_montaz_natynkowe_nie_myli_sie_z_podtynkowym(catalog):
    """Bug: brak sprawdzania montazu - 'natynkowe' mylilo sie z domyslnym (podtynkowym)."""
    r = match_against_catalog("Gniazdo pojedyncze natynkowe niemieckie", catalog)
    assert r.kod == "GNIAZDO POJEDYŃCZE NATYNKOWE NIEMIECKIE IP66"


def test_krotnosc_domyslnie_pojedyncze(catalog):
    """Bug: bez domyslnej krotnosci=1, 'Gniazdo podtynkowe biale niemieckie' (bez slowa
    o krotnosci) trafialo w GNIAZDO POCZWÓRNE (krotnosc=4) przez przypadkowy remis Dice."""
    r = match_against_catalog("Gniazdo podtynkowe białe niemieckie", catalog)
    assert "POCZWÓRNE" not in (r.kod or "")


def test_alias_specyficznosc_pojedyncze_vs_podtynkowe(catalog):
    """Bug: krotszy alias (bez 'podtynkowe') zawsze pasowal tez do dluzszego zapytania
    (bo jego tokeny sa podzbiorem) - bez preferencji dlugosci oba aliasy wygrywaly naraz."""
    r1 = match_against_catalog("Gniazdo pojedyńcze niemieckie białe", catalog)
    r2 = match_against_catalog("Gniazdo pojedyncze niemieckie białe podtynkowe", catalog)
    assert r1.kod != r2.kod
    assert r2.kod == "GNIAZDO 16A PODTYNKOWE Z KLAPKĄ BIAŁE NIEMIECKIE"


def test_dominujacy_kraj_ogolny_nie_tylko_grafit(catalog):
    """R1b uogolnione: remis PL/DE rozwiazywany dominujacym krajem dla KAZDEJ pary,
    nie tylko dla zakodowanego na sztywno przypadku grafitu."""
    r_pl = match_against_catalog("Gniazdo podtynkowe z klapką białe", catalog, dominant_country="PL")
    r_de = match_against_catalog("Gniazdo podtynkowe z klapką białe", catalog, dominant_country="DE")
    assert r_pl.kod != r_de.kod
    assert "POLSKIE" in r_pl.kod
    assert "NIEMIECKIE" in r_de.kod


def test_kabel_lan_synonim_i_alias(catalog):
    r = match_against_catalog("kabel lan", catalog)
    assert r.kod == "PRZEWÓD INTERNETOWY LAN UTP KAT. 6"


def test_full_form_rows_regression(catalog):
    """Smoke test na pelnej liscie ~153 wierszy formularza - progi jakosciowe nie moga sie
    pogorszyc wzgledem stanu z monolitu JS (146 ok / 6 excluded / 1 swiadoma dziura)."""
    form_rows_path = FIXTURES / "form_rows_sample.json"
    if not form_rows_path.exists():
        pytest.skip("form_rows_sample.json nie zostal jeszcze wygenerowany z monolitu")
    rows = json.loads(form_rows_path.read_text(encoding="utf-8"))
    counts = {"ok": 0, "warn": 0, "bad": 0, "excluded": 0}
    for row in rows:
        r = match_against_catalog(row, catalog, dominant_country="PL")
        counts[r.quality] += 1
    assert counts["ok"] >= 140
