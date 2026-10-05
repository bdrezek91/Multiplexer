"""Testy: import ROZDZIELNICA HERMETYCZNA 1X18 (GALANT) - zgloszenie pracownika, dokument
20261001135350826.pdf (2026-10-05). OCR rozpoznal "rozdzielnica GALANT PLUS RN-1x18 IP 65",
katalog nie mial zadnego produktu pod ta nazwa handlowa producenta."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.import_rozdzielnica_galant import KOD, import_rozdzielnica_galant


def test_import_tworzy_produkt(db_session):
    wynik = import_rozdzielnica_galant(db_session)

    assert "Utworzono produkt" in wynik
    assert KOD in wynik


def test_import_jest_idempotentny(db_session):
    import_rozdzielnica_galant(db_session)
    wynik = import_rozdzielnica_galant(db_session)

    assert "bez zmian" in wynik


def test_galant_plus_z_dokumentu_trafia_w_nowy_produkt(db_session, baza_elektryka_json):
    """Dokladny tekst z realnego zgloszenia pracownika."""
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnica_galant(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("rozdzielnica GALANT PLUS RN-1x18 IP 65", catalog)

    assert result.kod == KOD
    assert result.quality == "ok"


def test_samo_slowo_galant_trafia_w_produkt(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnica_galant(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Rozdzielnica Galant", catalog)

    assert result.kod == KOD
    assert result.quality == "ok"
