"""Test: scripts.uzupelnij_wago_cyfrowo.py - "Wago zamykane 2/3 przewodów" (zapis cyfrowy) musi
trafiac pewnie w PODWÓJNE/POTRÓJNE (zapis slowny w katalogu), tak jak juz dziala dla 4/5
przewodowych wariantow, ktore w katalogu SA nazwane cyfrowo (2026-09-29)."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.uzupelnij_wago_cyfrowo import uzupelnij


def test_uzupelnij_dopisuje_aliasy(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    wynik = uzupelnij(db_session)

    assert "WAGO ZAMYKANE PODWÓJNE" in wynik
    assert "WAGO ZAMYKANE POTRÓJNE" in wynik
    assert "2 przewody" in wynik
    assert "3 przewody" in wynik


def test_uzupelnij_jest_idempotentny(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    uzupelnij(db_session)
    wynik = uzupelnij(db_session)

    assert "(brak - juz istnialy)" in wynik


def test_wago_2_przewody_trafia_w_podwojne(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Wago zamykane 2 przewodów", catalog)

    assert result.kod == "WAGO ZAMYKANE PODWÓJNE"
    assert result.quality == "ok"


def test_wago_3_przewodow_trafia_w_potrojne(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Wago zamykane 3 przewodów", catalog)

    assert result.kod == "WAGO ZAMYKANE POTRÓJNE"
    assert result.quality == "ok"
