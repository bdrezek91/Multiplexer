"""
Testy regresyjne regul specjalnych (Etap 3) - port 1:1 z monolitu (special_rules.py, docstring).
Katalog z JSON (jak w test_matcher.py) - regula specjalne to domyslny zestaw z kodu
(DEFAULT_SPECIAL_RULES), bez zaleznosci od bazy danych (test integracyjny z baza - test_special_rules_db.py).
"""
import json
from pathlib import Path

import pytest

from app.modules.matcher import match_against_catalog
from app.modules.matcher.special_rules import _snap_to_step
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def test_lampa_na_szynoprzewod_wykluczona(catalog):
    """Lampa LED na szynoprzewod jest juz wliczona w zestaw lamp szynowych - nie dopasowujemy osobno."""
    r = match_against_catalog("Lampa LED na szynoprzewód biała", catalog)
    assert r.quality == "excluded"
    assert r.kod is None


def test_r3_szynoprzewod_czarny_do_zestawu(catalog):
    r = match_against_catalog("Szynoprzewód czarny 1mb", catalog)
    assert r.kod == "ZESTAW LAMPY SZYNOWE CZARNE"
    assert r.quality == "ok"


def test_r3_szynoprzewod_bialy_do_zestawu(catalog):
    r = match_against_catalog("Szynoprzewód biały 2mb", catalog)
    assert r.kod == "ZESTAW LAMPY SZYNOWE BIAŁE"
    assert r.quality == "ok"


def test_r6_grzejnik_zaokragla_do_najblizszej_mocy(catalog):
    r = match_against_catalog("Grzejnik 1800W", catalog)
    assert r.kod == "GRZEJNIK 2000W"


def test_r6_grzejnik_bez_mocy_domyslnie_2000w(catalog):
    r = match_against_catalog("Grzejnik…...............W", catalog)
    assert r.kod == "GRZEJNIK 2000W"


def test_r6_grzejnik_remis_wygrywa_mniejszy_krok():
    """Tie-break identyczny jak w JS: przy remisie (np. 750W rownoodlegle od 500 i 1000)
    wygrywa PIERWSZY krok w kolejnosci listy (mniejszy), bo porownanie jest scisle '<'."""
    assert _snap_to_step(750, [500, 1000, 1500, 2000]) == 500
    assert _snap_to_step(1750, [500, 1000, 1500, 2000]) == 1500


def test_ocr_override_wkret_ocynk(catalog):
    r = match_against_catalog("Wkręt ocynk 4,2x16", catalog)
    assert r.kod == "WKRĘT 4,2X16 (OCYNK) (50 SZT)"


def test_ocr_override_mbn316e(catalog):
    """Fragment kodu producenta czytelny mimo mocno znieksztalconego OCR reszty nazwy."""
    r = match_against_catalog("mbn316e", catalog)
    assert r.kod == "WYŁĄCZNIK NADPRĄDOWY 3P 16A"


def test_ocr_override_peszel(catalog):
    r = match_against_catalog("peszel", catalog)
    assert r.kod == "RURA KARBOWANA FI16"


@pytest.mark.parametrize("nazwa", [
    "Taśma LED 5M",
    "Taśma LED 10M",
    "Taśma LED zielona",
    "Zestaw taśma LED",
    "tasma led",
])
def test_kazda_tasma_led_wymuszona_na_tasme_do_dekorow(catalog, nazwa):
    """Na zyczenie uzytkownika (2026-08-31): dowolny wariant/kolor/dlugosc tasmy LED z kartki
    zawsze mapuje sie na jeden, ten sam kod - bez wzgledu na to, co dokladnie ktos dopisal."""
    r = match_against_catalog(nazwa, catalog)
    assert r.kod == "TAŚMA LED DO DEKORÓW"
    assert r.quality == "ok"


def test_r5_wariant_magazynowy_podstawia_kod(catalog):
    r_zabrze = match_against_catalog("Bezpiecznik 25A Niemiecki", catalog, magazyn="Zabrze")
    r_czekanow = match_against_catalog("Bezpiecznik 25A Niemiecki", catalog, magazyn="Czekanów")
    r_brak = match_against_catalog("Bezpiecznik 25A Niemiecki", catalog)

    assert r_zabrze.kod == "BEZPIECZNIK 25A NIEMIECKI"
    assert r_czekanow.kod == "BEZPIECZNIK 25A NIEMIECKI 1P"
    assert r_brak.kod == "BEZPIECZNIK 25A NIEMIECKI"


def test_stary_r1b_gniazdo_grafit_pokryty_regula_ogolna(catalog):
    """Stary, waski R1b z monolitu (twardo zakodowany tylko dla 'gniazdo z klapka grafit')
    NIE zostal przeniesiony do special_rules - ten test potwierdza, ze generalna regula
    dominujacego kraju (matcher/core.py) daje DOKLADNIE ten sam wynik dla tego przypadku."""
    r_brak = match_against_catalog("Gniazdo podtynkowe z klapką grafit", catalog)
    r_pl = match_against_catalog("Gniazdo podtynkowe z klapką grafit", catalog, dominant_country="PL")
    r_de = match_against_catalog("Gniazdo podtynkowe z klapką grafit", catalog, dominant_country="DE")

    assert r_brak.kod == r_pl.kod  # remis/brak danych -> PL (zasada z oryginalnego rekordu)
    assert "POLSKIE" in r_pl.kod
    assert "NIEMIECKIE" in r_de.kod
