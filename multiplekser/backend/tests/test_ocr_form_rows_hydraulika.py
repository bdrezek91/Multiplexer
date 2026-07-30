"""Testy Kroku Hydraulika-3: snap_to_known_item_hydraulika() - port snapToKnownItem() z
Multipekser_Hydraulika.html (dwupoziomowe dopasowanie FORM_ROWS -> ADDITIONAL_ROWS)."""
from app.modules.ocr.form_rows_hydraulika import ADDITIONAL_ROWS, FORM_ROWS, snap_to_known_item_hydraulika


def test_form_rows_ma_144_pozycje():
    assert len(FORM_ROWS) == 144


def test_additional_rows_ma_114_pozycji():
    assert len(ADDITIONAL_ROWS) == 114


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


def test_snap_zupelnie_obcy_tekst_jest_off():
    r = snap_to_known_item_hydraulika("Zupelnie inny obcy tekst spoza obu list XYZ123")
    assert r.status == "off"
    assert r.name == "Zupelnie inny obcy tekst spoza obu list XYZ123"


def test_snap_pusty_tekst_jest_off_z_zerowym_ratio():
    r = snap_to_known_item_hydraulika("")
    assert r.status == "off"
    assert r.ratio == 0.0
