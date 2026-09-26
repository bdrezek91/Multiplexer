"""Testy: import rozdzielnic Elegant + inteligentne rozroznianie wariantu "zwyklego" vs
"multimedialnego" po slowie-kwalifikatorze w tekscie OCR (2026-09-26)."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.import_rozdzielnice_elegant import PRODUCTS, import_rozdzielnice_elegant


def test_import_tworzy_oba_produkty(db_session):
    stats = import_rozdzielnice_elegant(db_session)

    assert stats["utworzone"] == len(PRODUCTS)
    assert stats["aliasy_dopisane"] == 0


def test_import_jest_idempotentny(db_session):
    import_rozdzielnice_elegant(db_session)
    stats = import_rozdzielnice_elegant(db_session)

    assert stats["utworzone"] == 0
    assert stats["aliasy_dopisane"] == 0
    assert stats["bez_zmian"] == len(PRODUCTS)


def test_bez_slowa_multimedialna_trafia_w_wariant_bazowy(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnice_elegant(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Rozdzielnica Elegant 24", catalog)

    assert result.kod == "ROZDZIELNICA ELEGANT 24"
    assert result.quality == "ok"


def test_ze_slowem_multimedialna_trafia_w_wariant_multimedialny(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnice_elegant(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Rozdzielnica Elegant multimedialna 24", catalog)

    assert result.kod == "ROZDZIELNICA ELEGANT MULTIMEDIALNA 24"
    assert result.quality == "ok"
