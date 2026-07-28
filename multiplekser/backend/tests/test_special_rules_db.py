"""Testy integracyjne Etapu 3: import special_rules do Postgresa + rules_from_db + uzycie w matchu."""
from app.modules.matcher import match_against_catalog, rules_from_db
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.import_special_rules import import_special_rules


def test_import_special_rules_tworzy_oczekiwana_liczbe(db_session):
    stats = import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    assert stats["utworzone"] == len(DEFAULT_SPECIAL_RULES)
    assert stats["zaktualizowane"] == 0


def test_import_special_rules_jest_idempotentny(db_session):
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)
    stats = import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    assert stats["utworzone"] == 0
    assert stats["zaktualizowane"] == len(DEFAULT_SPECIAL_RULES)


def test_rules_from_db_dziala_tak_samo_jak_default(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_special_rules(db_session, DEFAULT_SPECIAL_RULES)

    catalog = Catalog.from_db(db_session)
    rules_db = rules_from_db(db_session)

    r_default = match_against_catalog("Grzejnik 1800W", catalog, special_rules=DEFAULT_SPECIAL_RULES)
    r_db = match_against_catalog("Grzejnik 1800W", catalog, special_rules=rules_db)

    assert r_default.kod == r_db.kod == "GRZEJNIK 2000W"
