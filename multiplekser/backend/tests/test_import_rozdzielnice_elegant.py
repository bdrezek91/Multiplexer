"""Testy: import rozdzielnic Elegant + inteligentne rozroznianie wariantu "zwyklego" vs
"multimedialnego" po slowie-kwalifikatorze w tekscie OCR (2026-09-26)."""
from app.modules.matcher import match_against_catalog
from app.modules.ocr.form_rows_elektryka import reconcile_form_row, snap_to_form_row
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


def test_pelny_pipeline_snap_reconcile_match_z_dopiskiem_elegant(db_session, baza_elektryka_json):
    """Regresja bledu z 2026-09-26 - patrz test_ocr_form_rows.py:
    test_reconcile_zachowuje_dopisek_elegant. Bez naprawy snap_to_form_row() po cichu zamienialo
    'Rozdzielnica SRN 24 biała ELEGANT' na zwykly wiersz formularza, gubiac ELEGANT, i cala
    pozycja trafiala w zwykla ROZDZIELNICA SRN 24 zamiast w ROZDZIELNICA ELEGANT 24."""
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnice_elegant(db_session)
    catalog = Catalog.from_db(db_session)

    raw = "Rozdzielnica SRN 24 biała ELEGANT"
    snap = snap_to_form_row(raw)
    reconciled = reconcile_form_row(raw, snap)
    result = match_against_catalog(reconciled.nazwa, catalog)

    assert result.kod == "ROZDZIELNICA ELEGANT 24"
    assert result.quality == "ok"


def test_regula_specjalna_multimedialna_ma_pierwszenstwo_przed_elegant(db_session, baza_elektryka_json):
    """Nawet mocno "zaszumiony" tekst z obydwoma slowami-kwalifikatorami musi trafic w wariant
    multimedialny, nie w zwykly Elegant - reguly specjalne w special_rules.py sa sprawdzane w
    kolejnosci priority (multimedialna=78 PRZED elegant=79, patrz komentarz przy regulach)."""
    import_catalog(db_session, baza_elektryka_json)
    import_rozdzielnice_elegant(db_session)
    catalog = Catalog.from_db(db_session)

    raw = "Rozdzielnica SRN 24 biała ELEGANT multimedialna"
    snap = snap_to_form_row(raw)
    reconciled = reconcile_form_row(raw, snap)
    result = match_against_catalog(reconciled.nazwa, catalog)

    assert result.kod == "ROZDZIELNICA ELEGANT MULTIMEDIALNA 24"
    assert result.quality == "ok"
