"""Testy integracyjne Etapu 2: import katalogu do Postgresa + Catalog.from_db.

Wymaga bazy testowej (TEST_DATABASE_URL, domyslnie multiplekser_test na localhost).
"""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog


def test_import_tworzy_oczekiwana_liczbe_produktow(db_session, baza_elektryka_json):
    stats = import_catalog(db_session, baza_elektryka_json)

    assert stats["utworzone"] == 379 + 292
    assert stats["zaktualizowane"] == 0


def test_import_jest_idempotentny(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    stats = import_catalog(db_session, baza_elektryka_json)

    assert stats["utworzone"] == 0
    assert stats["zaktualizowane"] == 379 + 292


def test_catalog_from_db_zawiera_tylko_generyczne(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    catalog = Catalog.from_db(db_session)

    assert len(catalog.products) == 379
    assert all(p.status == "generyczny" for p in catalog.products)


def test_catalog_from_db_przenosi_aliasy_i_warianty_magazynowe(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    catalog = Catalog.from_db(db_session)

    bezpiecznik = catalog.find_by_kod("BEZPIECZNIK 25A NIEMIECKI")
    assert bezpiecznik is not None
    assert bezpiecznik.warianty_magazynowe == {
        "Zabrze": "BEZPIECZNIK 25A NIEMIECKI",
        "Czekanów": "BEZPIECZNIK 25A NIEMIECKI 1P",
    }

    francuski = catalog.find_by_kod("BEZPIECZNIK 10A FRANCUSKI")
    assert any("nadprądowy" in a.text for a in francuski.aliasy)


def test_match_against_catalog_z_bazy_dziala_jak_z_json(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    catalog_db = Catalog.from_db(db_session)
    catalog_json = Catalog.from_json_dict(baza_elektryka_json)

    query = "Bezpiecznik 10A francuski"
    result_db = match_against_catalog(query, catalog_db)
    result_json = match_against_catalog(query, catalog_json)

    assert result_db.kod == result_json.kod == "BEZPIECZNIK 10A FRANCUSKI"
    assert result_db.quality == result_json.quality == "ok"
