"""Testy modulu Parser dla Hydrauliki - ekstrakcja atrybutow (gwint/material/zlacze/srednica/
kat/dlugosc/pojemnosc), zgodna z logika uzyta przy budowie baza_hydraulika.json."""
from app.modules.parser.hydraulika import core_and_attrs_hydraulika


def test_gwint_pojedynczy():
    r = core_and_attrs_hydraulika("Zawór kątowy 1/2")
    assert r.gwint_cal == "1/2"


def test_gwint_zlozony_x():
    r = core_and_attrs_hydraulika("Zawór kątowy 1/2x3/4")
    assert r.gwint_cal == "1/2x3/4"


def test_material_pex():
    r = core_and_attrs_hydraulika("Łącznik kolankowy GW 16x1/2 PEX")
    assert r.material == "PEX"
    assert r.zlacze == "GW"


def test_srednica_fi():
    r = core_and_attrs_hydraulika("Kolanko kanalizacyjne fi 40 45 st")
    assert r.srednica_mm == 40.0
    assert r.kat_st == 45


def test_dlugosc_cm():
    r = core_and_attrs_hydraulika("Wąż 1/2x3/8 cala 40 cm")
    assert r.dlugosc_cm == 40


def test_pojemnosc_l():
    r = core_and_attrs_hydraulika("Bojler 80 L")
    assert r.pojemnosc_l == 80


def test_kolor_niezalezny_od_koloru_elektryki():
    r = core_and_attrs_hydraulika("Grzejnik łazienkowy 40x70 biały")
    assert r.kolor == "BIALY"
    assert r.wymiar_mm == "40x70"


def test_wymiar_pomijany_gdy_jest_gwint():
    """Gwint i wymiar fizyczny czasem wspolwystepuja w tym samym tekscie (np. dlugosc waza
    zapisana jako 'NxM') - gwint ma pierwszenstwo, wymiar_mm zostaje None."""
    r = core_and_attrs_hydraulika("Wąż 1/2x3/8 cala 40 cm")
    assert r.wymiar_mm is None
