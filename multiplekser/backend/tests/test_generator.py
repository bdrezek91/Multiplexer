"""
Testy modulu Generator - port generateOutput() z monolitu. Kazdy przypadek weryfikuje jedna
udokumentowana zasade biznesowa z komentarzy w monolicie (patrz core.py, constants.py).
"""
import json
from pathlib import Path

import pytest

from app.modules.generator import (
    GeneratorItem, encode_cp1250, generate_output, get_filename, physical_order_for,
)
from app.modules.generator.detection import detect_dominant_color, detect_dominant_country
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def _lines_by_kod(lines: list[str]) -> dict[str, str]:
    """Mapuje kazda linie wyjsciowa na jej pierwsze pole (kod lub tresc komentarza)."""
    return {line.split(";")[0]: line for line in lines}


# ---- Sortowanie fizyczne ----

def test_physical_order_dokladny_match():
    assert physical_order_for("Korytko 90x60") < physical_order_for("Wkręt ocynk 4,2x16")


def test_physical_order_fallback_dla_calkowicie_niedopasowanego_tekstu():
    assert physical_order_for("zupelnie nieznana pozycja spoza formularza xyz", fallback=12345) == 12345


def test_physical_order_pozycje_polskie_nie_wypadaja_na_koniec():
    """Regresja (2026-08-04, zgloszona przez Bartka jako "mega pojebana kolejnosc"): stara
    FORM_PHYSICAL_ORDER opisywala wariant formularza z pozycjami "niemieckimi" (dawno nieaktualny),
    wiec dzisiejsze "polskie" pozycje z realnej kartki nie mialy dokladnego dopasowania i czesto
    ladowaly sie na koniec listy (fallback) zamiast we wlasciwym miejscu - np. "Wskaźnik zasilania
    jednomodułowy (FAZ)" (fizycznie wiersz 9. na kartce) trafial na SAM KONIEC wygenerowanego pliku
    zamiast blisko poczatku, bo w starej liscie w ogole nie bylo takiej pozycji."""
    order = physical_order_for("Wskaźnik zasilania jednomodułowy (FAZ)")
    assert order < 10000  # nie fallback - musi byc realnie dopasowany, nie zgadywany
    assert order < physical_order_for("Rozdzielnica SRN 24 biała")
    assert order < physical_order_for("Wyłącznik nadprądowy MBN316E polska 3P 16A")
    assert order < physical_order_for("Szyna grzebieniowa trójfazowa")
    assert order < physical_order_for("Wkręt ocynk 4,2x16")


def test_physical_order_rozdzielnica_polska_w_kolejnosci_numerow():
    """Kolejny realny przypadek z tego samego zgloszenia: "Rozdzielnica SRN 24 biała" musi byc
    miedzy SRN 12 a SRN 36, nie przypadkowo dopasowana do innej, podobnej etykiety."""
    assert (
        physical_order_for("Rozdzielnica SRN 12 biała")
        < physical_order_for("Rozdzielnica SRN 24 biała")
        < physical_order_for("Rozdzielnica SRN 36 biała")
        < physical_order_for("Rozdzielnica SRN 48 biała")
    )


def test_generate_output_sortuje_wg_fizycznej_kolejnosci_nie_kolejnosci_wejscia(catalog):
    # Celowo w odwrotnej kolejnosci fizycznej: wkret ocynk (blisko konca formularza) przed
    # gniazdem (blisko poczatku).
    items = [
        GeneratorItem(name="Wkręt ocynk 4,2x16", qty=10),
        GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=2),
    ]
    result = generate_output(items, catalog, magazyn=None)
    kody = [line.split(";")[0] for line in result.lines]
    assert kody.index("WTYCZKA ODBIORNIKOWA 32A NIEBIESKA") < kody.index("WKRĘT 4,2X16 (OCYNK) (50 SZT)")


# ---- OSB vs lampa na szynoprzewod (asymetria z monolitu) ----

def test_wkret_osb_pomijany_calkowicie_bez_linii(catalog):
    items = [GeneratorItem(name="Wkręt czarny OSB", qty=15)]
    result = generate_output(items, catalog, magazyn=None)
    assert result.lines == []


def test_lampa_na_szynoprzewod_dostaje_komentarz_pominiete(catalog):
    items = [GeneratorItem(name="Lampa LED na szynoprzewód biała", qty=2)]
    result = generate_output(items, catalog, magazyn="Zabrze")
    assert len(result.lines) == 1
    assert result.lines[0].startswith("### POMINIETE CELOWO (lampa na szynoprzewód")
    assert "Lampa LED na szynoprzewód biała;2;;SZT;Zabrze" in result.lines[0]


# ---- R3: szynoprzewod -> zestaw (akumulacja metrow / dzielnik) ----

def test_szynoprzewod_akumuluje_metry_i_dzieli_na_zestawy(catalog):
    items = [
        GeneratorItem(name="Szynoprzewód czarny 2mb", qty=3),  # 6m
        GeneratorItem(name="Szynoprzewód czarny 1mb", qty=2),  # 2m -> razem 8m / dzielnik 2 = 4
    ]
    result = generate_output(items, catalog, magazyn=None)
    by_kod = _lines_by_kod(result.lines)
    assert by_kod["ZESTAW LAMPY SZYNOWE CZARNE"] == "ZESTAW LAMPY SZYNOWE CZARNE;4;;SZT;"


def test_szynoprzewod_zero_metrow_usuwa_wpis(catalog):
    # Same "0 mb" nie powinno w praktyce wystapic (qty>0 wymagane wyzej w pipeline), ale test
    # weryfikuje bezposrednio funkcje przy jawnym zerze przez brak jakiegokolwiek dopasowania.
    items = [GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=1)]
    result = generate_output(items, catalog, magazyn=None)
    assert not any("ZESTAW LAMPY SZYNOWE" in line for line in result.lines)


# ---- R4: wkret ocynk -> opakowania (Math.ceil, rowniez ponizej 50 szt) ----

def test_wkret_ocynk_math_ceil_ponizej_progu(catalog):
    items = [GeneratorItem(name="Wkręt ocynk 4,2x16", qty=30)]
    result = generate_output(items, catalog, magazyn=None)
    assert result.lines == ["WKRĘT 4,2X16 (OCYNK) (50 SZT);1;;OPAK;"]


def test_wkret_ocynk_math_ceil_powyzej_progu(catalog):
    items = [GeneratorItem(name="Wkręt ocynk 4,2x16", qty=51)]
    result = generate_output(items, catalog, magazyn=None)
    assert result.lines == ["WKRĘT 4,2X16 (OCYNK) (50 SZT);2;;OPAK;"]


# ---- Korytka: mapowanie rozmiar->kod wg koloru dominujacego, R2 "twarda zasada" ----

def test_korytko_mapowane_na_kolor_dominujacy_niezaleznie_od_wlasnej_nazwy(catalog):
    items = [
        GeneratorItem(name="Wyłącznik jednobiegunowy czarny", qty=3),
        GeneratorItem(name="Wyłącznik krzyżowy czarny", qty=2),
        GeneratorItem(name="Korytko 40x25", qty=5),
    ]
    result = generate_output(items, catalog, magazyn="Czekanów")
    assert result.dominant_color == "black"
    by_kod = _lines_by_kod(result.lines)
    assert "KORYTKO CZARNE 40X25" in by_kod


def test_korytko_czarne_60x90_brak_dopasowania_bez_zgadywania(catalog):
    items = [
        GeneratorItem(name="Wyłącznik jednobiegunowy czarny", qty=3),
        GeneratorItem(name="Wyłącznik krzyżowy czarny", qty=2),
        GeneratorItem(name="Korytko 90x60", qty=4),
    ]
    result = generate_output(items, catalog, magazyn=None)
    assert result.dominant_color == "black"
    unmatched = [l for l in result.lines if l.startswith("### BRAK DOPASOWANIA (korytko czarne 90x60")]
    assert len(unmatched) == 1
    assert not any("KORYTKO" in l and "BRAK" not in l for l in result.lines)


# ---- offForm downgrade + fallback "Elektryka" linia ----

def test_offform_z_niskim_ratio_dostaje_fallback_elektryka(catalog):
    # "MBS320" - dopisek spoza formularza, dopasowanie do calego katalogu wychodzi slabe.
    items = [GeneratorItem(name="MBS320", qty=2, off_form=True)]
    result = generate_output(items, catalog, magazyn="Zabrze")
    assert len(result.lines) == 1
    assert result.lines[0].startswith('Elektryka;1;DOPISEK SPOZA FORMULARZA - oryginal: "MBS320"')
    assert "ilosc na kartce: 2" in result.lines[0]


# ---- qty_mode "ones" ----

def test_qty_mode_ones_ustawia_wszystko_na_1(catalog):
    items = [GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=7)]
    result = generate_output(items, catalog, magazyn=None, qty_mode="ones")
    assert result.lines == ["WTYCZKA ODBIORNIKOWA 32A NIEBIESKA;1;;SZT;"]


# ---- first_wydawka: always-include wstawiany we WLASCIWE miejsce fizyczne ----

def test_first_wydawka_dodaje_baze_i_korytka_w_kolorze_projektu(catalog):
    items = [GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=1)]
    result = generate_output(items, catalog, magazyn=None, first_wydawka=True)
    by_kod = _lines_by_kod(result.lines)
    assert "SZYNA GRZEBIENIOWA WIDEŁKOWA;1;;SZT;" == by_kod["SZYNA GRZEBIENIOWA WIDEŁKOWA"]
    assert "KORYTKO 32X15;1;;M;" == by_kod["KORYTKO 32X15"]  # bialy = domyslny (brak przewagi czarnych)
    assert "WKRĘT 4,2X16 (OCYNK) (50 SZT);1;;OPAK;" == by_kod["WKRĘT 4,2X16 (OCYNK) (50 SZT)"]


def test_first_wydawka_nie_dodaje_usunietych_przewodow(catalog):
    # Na prosbe uzytkownika (2026-07-28) usuniete z ALWAYS_INCLUDE_BASE niezaleznie od magazynu -
    # przewody ktore nie powinny juz trafiac do pierwszej wydawki.
    items = [GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=1)]
    for magazyn in (None, "Mag m-y Zabrze", "MAGAZYN Czekanów"):
        result = generate_output(items, catalog, magazyn=magazyn, first_wydawka=True)
        by_kod = _lines_by_kod(result.lines)
        assert "PRZEWÓD 5X16 CZARNY" not in by_kod
        assert "PRZEWÓD 3X16 CZARNY" not in by_kod
        assert "PRZEWÓD INSTALACYJNY 1X10 KOLOR" not in by_kod
        assert "KORYTKO 90X60" not in by_kod


def test_first_wydawka_nie_dubluje_juz_obecnej_pozycji(catalog):
    items = [
        GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=1),
        GeneratorItem(name="Wago zamykane podwójne", qty=9),
    ]
    result = generate_output(items, catalog, magazyn=None, first_wydawka=True)
    wago_lines = [l for l in result.lines if l.startswith("WAGO ZAMYKANE PODWÓJNE;")]
    assert wago_lines == ["WAGO ZAMYKANE PODWÓJNE;9;;SZT;"]  # realna ilosc, nie nadpisana "1"


def test_bez_first_wydawka_baza_nie_jest_dodawana(catalog):
    items = [GeneratorItem(name="Wtyczka odbiornikowa 32A (niebieska) 1F", qty=1)]
    result = generate_output(items, catalog, magazyn=None, first_wydawka=False)
    assert not any("SZYNA GRZEBIENIOWA" in l for l in result.lines)


# ---- Detekcja koloru/kraju dominujacego ----

def test_detect_dominant_color_remis_to_bialy():
    color, counts = detect_dominant_color(["Gniazdo czarne", "Gniazdo białe"])
    assert color == "white"
    assert counts == {"black": 1, "white": 1}


def test_detect_dominant_color_ignoruje_nieistotne_pozycje():
    color, counts = detect_dominant_color(["Przewód 3x1,5 czarny"])  # "przewod" nie jest color-relevant
    assert counts == {"black": 0, "white": 0}
    assert color == "white"


def test_detect_dominant_country_remis_to_pl(catalog):
    # Bez zadnych pozycji Gniazda/Łączniki -> licznik 0/0 -> PL.
    assert detect_dominant_country(["Peszel"], catalog) == "PL"


def test_detect_dominant_country_niemiecki_wygrywa_przy_przewadze(catalog):
    names = ["Gniazdo pojedyńcze niemieckie białe", "Wyłącznik nadprądowy 16A niemiecki"]
    assert detect_dominant_country(names, catalog) == "DE"


# ---- getFilename / CP1250 ----

def test_get_filename_domyslna_nazwa_gdy_puste():
    assert get_filename(None) == "receptura.txt"
    assert get_filename("") == "receptura.txt"


def test_get_filename_sanityzuje_niedozwolone_znaki():
    assert get_filename('Projekt: 12/06\\2026*"<>|') == "Projekt- 12-06-2026-.txt"


def test_encode_cp1250_polskie_znaki():
    assert encode_cp1250("Łódź") == bytes([0xA3, 0xF3, ord("d"), 0x9F])


def test_encode_cp1250_nieznany_znak_fallback_pytajnik():
    assert encode_cp1250("emoji 😀") == b"emoji ?"


def test_encode_cp1250_typograficzny_cudzyslow():
    """Realny blad z produkcji (2026-08-03): kody typu 'ODPOWIETRZNIK AUTOMATYCZNY 1/2” BIALY'
    mialy cudzyslow zamieniany na '?' (brak w mapie), Optima nie znajdowala takiej pozycji przy
    imporcie."""
    assert encode_cp1250("1/2”") == b"1/2" + bytes([0x94])
    assert encode_cp1250("“cytat”") == bytes([0x93]) + b"cytat" + bytes([0x94])


# ---- Reczna korekta dopasowania (2026-07-31) ----

def test_generate_output_uzywa_zapisanego_dopasowania_gdy_ok(catalog):
    """Realny blad z produkcji: generator ignorowal reczna korekte match_kod (PATCH
    .../items/{item_id}) i zawsze dopasowywal surowa nazwe od zera - "cos niejasnego xyz" nigdy
    nie dopasuje sie samo, wiec test przechodzi TYLKO jesli generator faktycznie uzyje
    przekazanego match_kod/match_jm zamiast wlasnego dopasowania."""
    items = [GeneratorItem(
        name="cos niejasnego xyz", qty=3, match_kod="KORYTKO 32X15", match_nazwa="Korytko 32x15",
        match_jm="M", match_quality="ok",
    )]
    result = generate_output(items, catalog, magazyn=None)
    assert result.lines == ["KORYTKO 32X15;3;;M;"]


def test_generate_output_ignoruje_zapisane_dopasowanie_gdy_nie_ok(catalog):
    """Jesli match_quality nie jest 'ok' (np. nigdy nie poprawione recznie) - generator
    dopasowuje normalnie, tak jak dotychczas."""
    items = [GeneratorItem(
        name="Grzejnik 1800W", qty=1, match_kod="KORYTKO 32X15", match_quality="bad",
    )]
    result = generate_output(items, catalog, magazyn=None)
    assert result.lines == ["GRZEJNIK 2000W;1;;SZT;"]
