"""Testy: import pokryw KOPOS do korytek LHD 40x20/40x40 (2026-09-18) - patrz docstring skryptu
i historia czatu (odreczny dopisek na formularzu w polu "INNE": "NAROŻNIK DO KORYT 8635/HF")."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.import_kopos_pokrywy_koryt import PRODUCTS, import_kopos_pokrywy_koryt


def test_import_tworzy_wszystkie_produkty(db_session):
    stats = import_kopos_pokrywy_koryt(db_session)

    assert stats["utworzone"] == len(PRODUCTS)
    assert stats["aliasy_dopisane"] == 0


def test_import_jest_idempotentny(db_session):
    import_kopos_pokrywy_koryt(db_session)
    stats = import_kopos_pokrywy_koryt(db_session)

    assert stats["utworzone"] == 0
    assert stats["aliasy_dopisane"] == 0
    assert stats["bez_zmian"] == len(PRODUCTS)


def test_naroznik_do_koryt_z_odrecznym_dopiskiem_trafia_we_wlasciwy_kod(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_kopos_pokrywy_koryt(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("NAROŻNIK DO KORYT 8635/HF", catalog)

    assert result.kod == "KOPOS POKRYWA NAROŻNA WEWN. (LHD 40X20) 8635 FB"
    assert result.quality == "ok"


def test_zakonczenie_do_koryt_z_odrecznym_dopiskiem_trafia_we_wlasciwy_kod(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_kopos_pokrywy_koryt(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("ZAKOŃCZENIE DO KORYT 8631/HF", catalog)

    assert result.kod == "KOPOS POKRYWA KOŃCOWA (LHD 40X20) 8631 FB"
    assert result.quality == "ok"
