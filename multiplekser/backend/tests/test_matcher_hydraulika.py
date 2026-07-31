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


def test_blaty_kuchenne_wymiar_rozrozniany(catalog):
    """Realny blad z produkcji (2026-07-30): 'Blat kuchenny 1250x600' i 'Blat kuchenny 825x600'
    oba mylnie dopasowywane do 'BLAT KUCHENNY 1200X600' - matcher Hydrauliki w ogole nie
    porownywal atrybutu wymiar_mm (byl ekstrahowany przez parser, ale pomijany przy liczeniu
    konfliktow), wiec cala rodzina "Blat kuchenny {wymiar}" remisowala i zawsze wygrywal
    pierwszy w kolejnosci katalogu."""
    r1200 = match_against_catalog_hydraulika("Blat kuchenny 1200x600", catalog)
    r1250 = match_against_catalog_hydraulika("Blat kuchenny 1250x600", catalog)
    r825 = match_against_catalog_hydraulika("Blat kuchenny 825x600", catalog)
    assert r1200.kod == "BLAT KUCHENNY 1200X600"
    assert r1250.kod == "BLAT KUCHENNY 1250X600"
    assert r825.kod == "BLAT KUCHENNY 825X600"
    assert len({r1200.kod, r1250.kod, r825.kod}) == 3


def test_full_catalog_smoke(catalog):
    """Smoke test na calym katalogu (kody jako wlasne zapytania - najlatwiejszy przypadek,
    powinien dawac wysoki odsetek 'ok') - punkt odniesienia do przyszlych poprawek."""
    counts = {"ok": 0, "warn": 0, "bad": 0, "excluded": 0}
    db = json.loads((FIXTURES / "baza_hydraulika.json").read_text(encoding="utf-8"))
    for rec in db["generyczne"].values():
        r = match_against_catalog_hydraulika(rec["nazwa"], catalog)
        counts[r.quality] += 1
    assert counts["ok"] >= 200  # z 249 generycznych


def test_skroty_z_dopiskow_poza_formularzem(catalog):
    """Realny przypadek z produkcji (2026-07-31): dopiski pod tabela pisane skrotowo -
    "silikon san"/"automat czarny"/"automat bialy"/"grzejnik czarny"/"grzejnik bialy" - musza
    trafiac na wlasciwy kod przez alias, niezaleznie od tego, jak dobrze OCR odczyta reszte
    dopisku (patrz tez prompt.py, DOPISKI POZA TABELĄ w Hydraulice)."""
    r_silikon = match_against_catalog_hydraulika("Silikon san", catalog)
    assert r_silikon.kod == "SILIKON SANITARNY"
    assert r_silikon.quality == "ok"

    r_automat_czarny = match_against_catalog_hydraulika("Automat czarny", catalog)
    assert r_automat_czarny.kod == "ODPOWIETRZNIK AUTOMATYCZNY 1/2” CZARNY"
    assert r_automat_czarny.quality == "ok"

    r_automat_bialy = match_against_catalog_hydraulika("Automat biały", catalog)
    assert r_automat_bialy.kod == "ODPOWIETRZNIK AUTOMATYCZNY 1/2” BIAŁY"
    assert r_automat_bialy.quality == "ok"

    r_grzejnik_czarny = match_against_catalog_hydraulika("Grzejnik czarny", catalog)
    assert r_grzejnik_czarny.kod == "GRZEJNIK ŁAZIENKOWY 40X70 CZARNY"
    assert r_grzejnik_czarny.quality == "ok"

    r_grzejnik_bialy = match_against_catalog_hydraulika("Grzejnik biały", catalog)
    assert r_grzejnik_bialy.kod == "GRZEJNIK ŁAZIENKOWY 40X70 BIAŁY"
    assert r_grzejnik_bialy.quality == "ok"


def test_jednostki_niezgodne_z_optima_poprawione(catalog):
    """Realny przypadek z produkcji (2026-07-31): eksport do Optimy zglaszal blad "Nie
    znaleziono jednostki SZT" dla tych kodow - caly plik seed mial wszedzie domyslnie SZT,
    mimo ze te konkretne pozycje sa w Optimie zdefiniowane w innej jednostce (patrz tez
    formularz papierowy, kolumna Jednostka)."""
    assert catalog.find_by_kod("RURA PP FI 20").jm == "M"
    assert catalog.find_by_kod("SZAFKA Z UMYWALKĄ 50 CM").jm == "KPL"
    assert catalog.find_by_kod("SZAFKA Z UMYWALKĄ 50 CM CZARNA").jm == "KPL"
    assert catalog.find_by_kod("ZLEW KUCHENNY CZARNY + BATERIA + KOSZYCZEK + SYFON").jm == "KPL"
