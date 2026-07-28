"""Testy Etapu 6: snap_to_form_row()/reconcile_form_row() - port snapToFormRow() z monolitu."""
from app.modules.ocr.form_rows import FORM_ROWS, reconcile_form_row, snap_to_form_row


def test_form_rows_ma_153_pozycje():
    """Dokladna liczba wierszy szablonu wyciagnieta programowo z index.html (Etap 0 analiza)."""
    assert len(FORM_ROWS) == 153


def test_snap_dokladne_dopasowanie_jest_exact():
    r = snap_to_form_row("Grzejnik…...............W")
    assert r.status == "exact"
    assert r.ratio >= 0.95


def test_snap_literowka_jest_fixed_i_poprawiona():
    r = snap_to_form_row("Kortyko 32x15")
    assert r.status == "fixed"
    assert r.name == "Korytko 32x15"


def test_snap_zupelnie_obcy_tekst_jest_off():
    r = snap_to_form_row("Zupelnie inny obcy tekst spoza formularza XYZ123")
    assert r.status == "off"
    assert r.name == "Zupelnie inny obcy tekst spoza formularza XYZ123"


def test_reconcile_zachowuje_realna_roznice_montazu():
    """Bug wykryty 2026-07-27: 'natynkowe' nie moze zostac po cichu zamienione na dopasowany
    wiersz formularza z 'podtynkowe' - to inny, realny produkt, nie literowka OCR."""
    raw = "Gniazdo pojedyncze niemieckie natynkowe"
    snap = snap_to_form_row(raw)
    assert snap.status == "fixed"  # tekstowo bardzo blisko wiersza formularza

    rec = reconcile_form_row(raw, snap)
    assert rec.nazwa == raw  # ale realna roznica (natynkowe) zostaje zachowana
    assert rec.uncertain is True


def test_reconcile_akceptuje_poprawke_gdy_tylko_literowka():
    raw = "Kortyko 32x15"
    snap = snap_to_form_row(raw)
    rec = reconcile_form_row(raw, snap)
    assert rec.nazwa == "Korytko 32x15"
    assert rec.uncertain is False
    assert "poprawiono" in rec.form_note


def test_reconcile_off_form_oznaczony_jako_niepewny():
    raw = "Zupelnie inny obcy tekst spoza formularza XYZ123"
    snap = snap_to_form_row(raw)
    rec = reconcile_form_row(raw, snap)
    assert rec.nazwa == raw
    assert rec.uncertain is True
    assert "spoza formularza" in rec.form_note
