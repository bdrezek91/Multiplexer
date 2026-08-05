"""Testy Kroku Hydraulika-3: snap_to_known_item_hydraulika() - port snapToKnownItem() z
Multipekser_Hydraulika.html (dwupoziomowe dopasowanie FORM_ROWS -> ADDITIONAL_ROWS)."""
from app.modules.ocr.form_rows_hydraulika import ADDITIONAL_ROWS, FORM_ROWS, snap_to_known_item_hydraulika


def test_form_rows_ma_145_pozycji():
    """145, nie 144 - "Rura fi 32 100 cm" dopisana pozniej (prawdziwy wiersz formularza
    pominiety przy pierwotnym porcie, patrz docs/RAPORT_OCR_NIEZAWODNOSC_2.md)."""
    assert len(FORM_ROWS) == 145


def test_snap_rura_fi_32_100_cm_nie_myli_sie_z_50_cm():
    """Realny przypadek z produkcji: przed dopisaniem tego wiersza "Rura fi 32 100 cm"
    dopasowywalo sie fuzzy-matchingiem do istniejacego "Rura fi 32 50 cm" (ta sama srednica,
    zla dlugosc) - dokladny wiersz w FORM_ROWS musi wygrywac jako "exact", nie "fixed" na cudzy
    wiersz."""
    r = snap_to_known_item_hydraulika("Rura fi 32 100 cm")
    assert r.name == "Rura fi 32 100 cm"
    assert r.status == "exact"


def test_additional_rows_ma_115_pozycji():
    """115, nie 114 - "Silikon sanitarny" dopisany pozniej (patrz prompt.py, dopisek
    DOPISKI POZA TABELĄ w Hydraulice)."""
    assert len(ADDITIONAL_ROWS) == 115


def test_snap_dokladne_dopasowanie_formularza_jest_exact():
    r = snap_to_known_item_hydraulika("Kolanko kanalizacyjne fi 32 45 st")
    assert r.status == "exact"
    assert r.ratio >= 0.95


def test_snap_literowka_w_formularzu_jest_fixed():
    r = snap_to_known_item_hydraulika("Kolanko kanalizacyjne fi 32 45  st.")
    assert r.status in ("exact", "fixed")


def test_snap_pozycja_tylko_z_bazy_dodatkowej_jest_additional():
    """'Grzejnik 1000W' istnieje WYLACZNIE w ADDITIONAL_ROWS, nie w FORM_ROWS (formularz glowny
    ma tylko 'Grzejnik łazienkowy ...') - musi trafic do drugiego poziomu dopasowania."""
    r = snap_to_known_item_hydraulika("Grzejnik 1000W")
    assert r.status == "additional"
    assert r.name == "Grzejnik 1000W"


def test_dokladny_waz_20_cm_z_bazy_dodatkowej_nie_zmienia_sie_na_30_cm():
    r = snap_to_known_item_hydraulika("Wąż 1/2x1/2 cala 20 cm")
    assert r.status == "additional"
    assert r.ratio == 1.0
    assert r.name == "Wąż 1/2x1/2 cala 20 cm"


def test_snap_zupelnie_obcy_tekst_jest_off():
    r = snap_to_known_item_hydraulika("Zupelnie inny obcy tekst spoza obu list XYZ123")
    assert r.status == "off"
    assert r.name == "Zupelnie inny obcy tekst spoza obu list XYZ123"


def test_snap_pusty_tekst_jest_off_z_zerowym_ratio():
    r = snap_to_known_item_hydraulika("")
    assert r.status == "off"
    assert r.ratio == 0.0
