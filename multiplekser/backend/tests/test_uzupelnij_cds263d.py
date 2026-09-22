"""Test: scripts.uzupelnij_cds263d.py - jednorazowa korekta danych, patrz docstring skryptu.
Uzupelnia atrybuty i alias istniejacego produktu "Wylacznik roznicoopradowy 2P CDS263D", zeby
odreczny opis z formularza ("rozniciowka niemiecka 1 fazowa 63A", bez podania kodu) trafial we
wlasciwy kod."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.uzupelnij_cds263d import uzupelnij


def test_uzupelnij_dopisuje_atrybuty_i_alias(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    wynik = uzupelnij(db_session)

    assert "CDS263D" in wynik
    assert "dopisany" in wynik


def test_uzupelnij_jest_idempotentny(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    uzupelnij(db_session)
    wynik = uzupelnij(db_session)

    assert "juz istnial" in wynik
    assert "brak - juz byly ustawione" in wynik


def test_opis_z_formularza_bez_kodu_trafia_we_wlasciwy_produkt(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Różnicówka niemiecka 1 fazowa 63A", catalog)

    assert result.kod is not None and "CDS263D" in result.kod
    assert result.quality == "ok"
