"""Testy row_groups.py - automatyczne wykrywanie grup niemal identycznych wierszy formularza
(2026-09-17), uzywane przez druga, niezalezna kontrole AI (ocr/verify.py:
verify_row_group_alignment, wpieta w documents/tasks.py: _check_row_group_alignment)."""
from app.modules.ocr.form_rows_elektryka import FORM_ROWS as FORM_ROWS_ELEKTRYKA
from app.modules.ocr.form_rows_hydraulika import FORM_ROWS as FORM_ROWS_HYDRAULIKA
from app.modules.ocr.row_groups import group_similar_rows


def test_grupuje_wiersze_roznace_sie_tylko_liczba():
    groups = group_similar_rows([
        "Rozdzielnica SRN 12 biała", "Rozdzielnica SRN 24 biała",
        "Rozdzielnica SRN 36 biała", "Rozdzielnica SRN 48 biała",
    ])
    assert groups == [[
        "Rozdzielnica SRN 12 biała", "Rozdzielnica SRN 24 biała",
        "Rozdzielnica SRN 36 biała", "Rozdzielnica SRN 48 biała",
    ]]


def test_grupuje_kable_roznace_sie_przekrojem():
    # Realny przypadek produkcyjny (2026-09-17): dokladnie ta grupa zostala pomylona o dwa
    # wiersze przez glowny model OCR - patrz test_documents_task.py.
    groups = group_similar_rows(["Przewód 3x1,5", "Przewód 3x2,5", "Przewód 3x4", "Puszka pusta 86x86"])
    assert ["Przewód 3x1,5", "Przewód 3x2,5", "Przewód 3x4"] in groups


def test_pojedyncza_etykieta_nie_tworzy_grupy():
    groups = group_similar_rows(["Grzejnik 1800W", "Czujnik zmierzchu"])
    assert groups == []


def test_puste_i_bez_cyfr_nie_grupuja_sie_przypadkowo():
    groups = group_similar_rows(["Czujnik zmierzchu", "Czujnik ruchu"])
    assert groups == []


def test_grupy_z_prawdziwego_formularza_elektryki_zawieraja_znane_przypadki():
    groups = group_similar_rows(FORM_ROWS_ELEKTRYKA)
    flat = {label for group in groups for label in group}
    # Grupy juz wymienione jako przyklady w prompt.py (_PODOBNE_WIERSZE_DOPISEK) - musza tez
    # zostac wykryte automatycznie, inaczej druga kontrola by ich nie objela.
    assert "Rozdzielnica SRN 24 biała" in flat
    assert "Wyłącznik nadprądowy 10A polski" in flat
    # Grupa, ktora NIE byla wymieniona z nazwy i zostala realnie pomylona (2026-09-17).
    assert "Przewód 3x4" in flat
    assert "Przewód 3x1,5" in flat


def test_grupy_z_prawdziwego_formularza_hydrauliki_zawieraja_znane_przypadki():
    groups = group_similar_rows(FORM_ROWS_HYDRAULIKA)
    flat = {label for group in groups for label in group}
    assert "Bojler 50 L" in flat
    assert "Bojler 80 L" in flat
