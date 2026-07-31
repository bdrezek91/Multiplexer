"""Testy integracyjne Etapu 2: import katalogu do Postgresa + Catalog.from_db.

Wymaga bazy testowej (TEST_DATABASE_URL, domyslnie multiplekser_test na localhost).
"""
import json
from pathlib import Path

from app.modules.matcher import match_against_catalog, match_against_catalog_hydraulika
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog

_HYDRAULIKA_FIXTURE = Path(__file__).parent / "fixtures" / "baza_hydraulika.json"


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


# ---- Krok Hydraulika-1: separacja logiczna dzialow (kolumna `dzial`) ----

def test_import_hydraulika_tworzy_oczekiwana_liczbe_produktow(db_session):
    baza_hydraulika = json.loads(_HYDRAULIKA_FIXTURE.read_text(encoding="utf-8"))
    stats = import_catalog(db_session, baza_hydraulika, dzial="hydraulika")

    assert stats["utworzone"] == 249 + 7
    assert stats["zaktualizowane"] == 0


def test_dzial_izolacja_elektryka_i_hydraulika_nie_mieszaja_sie(db_session, baza_elektryka_json):
    baza_hydraulika = json.loads(_HYDRAULIKA_FIXTURE.read_text(encoding="utf-8"))
    import_catalog(db_session, baza_elektryka_json, dzial="elektryka")
    import_catalog(db_session, baza_hydraulika, dzial="hydraulika")

    elektryka_catalog = Catalog.from_db(db_session, dzial="elektryka")
    hydraulika_catalog = Catalog.from_db(db_session, dzial="hydraulika")

    assert len(elektryka_catalog.products) == 379
    assert len(hydraulika_catalog.products) == 249
    assert all(p.dzial == "elektryka" for p in elektryka_catalog.products)
    assert all(p.dzial == "hydraulika" for p in hydraulika_catalog.products)

    # "GRZEJNIK 1000W" istnieje w OBU dzialach niezaleznie (elektryczny grzejnik nascienny
    # vs. grzejnik hydrauliki) - kod nie jest juz unikalny globalnie (uq_product_kod_dzial),
    # a Catalog danego dzialu musi zwrocic WLASCIWY rekord, nie ten z drugiego dzialu.
    elektryka_grzejnik = elektryka_catalog.find_by_kod("GRZEJNIK 1000W")
    hydraulika_grzejnik = hydraulika_catalog.find_by_kod("GRZEJNIK 1000W")
    assert elektryka_grzejnik is not None and hydraulika_grzejnik is not None
    assert elektryka_grzejnik.dzial == "elektryka"
    assert hydraulika_grzejnik.dzial == "hydraulika"
    assert elektryka_grzejnik.grupa != hydraulika_grzejnik.grupa

    # Matcher Hydrauliki dziala na jej wlasnym katalogu z bazy identycznie jak z JSON.
    catalog_json = Catalog.from_json_dict(baza_hydraulika, dzial="hydraulika")
    query = "Zawór kątowy 1/2x3/4"
    result_db = match_against_catalog_hydraulika(query, hydraulika_catalog)
    result_json = match_against_catalog_hydraulika(query, catalog_json)
    assert result_db.kod == result_json.kod == "ZAWÓR KĄTOWY 1/2X3/4"


def test_product_dzial_domyslny_to_elektryka(db_session, baza_elektryka_json):
    """Backward-compat: istniejace wywolania bez `dzial` (routery /match, /documents) musza
    dalej dzialac dokladnie jak przed dodaniem kolumny - filtr domyslny to 'elektryka'."""
    import_catalog(db_session, baza_elektryka_json, dzial="elektryka")

    catalog = Catalog.from_db(db_session)

    assert len(catalog.products) == 379
    assert all(p.dzial == "elektryka" for p in catalog.products)
