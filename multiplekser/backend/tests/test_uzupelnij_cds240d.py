"""Test: scripts.uzupelnij_cds240d.py - jednorazowa korekta danych, patrz docstring skryptu.
Dopisuje alias istniejacego produktu "Różnicówka niemiecka CDS240D", zeby odreczny opis z
formularza ("różnicówka niemiecka 1 fazowa 40A" albo po prostu "40A" bez fazy) trafial w niego
pewnie, a jednoczesnie explicit "3 fazowa 40A" nadal trafial we wlasciwy, osobny kod (CDC440J)."""
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog
from scripts.import_catalog import import_catalog
from scripts.uzupelnij_cds240d import uzupelnij


def test_uzupelnij_dopisuje_atrybuty_i_aliasy(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    wynik = uzupelnij(db_session)

    assert "CDS240D" in wynik
    assert "niemiecka 40a" in wynik


def test_uzupelnij_jest_idempotentny(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)

    uzupelnij(db_session)
    wynik = uzupelnij(db_session)

    assert "(brak - juz istnialy)" in wynik
    assert "(brak - juz byly ustawione)" in wynik


def test_opis_1_fazowy_bez_kodu_trafia_w_cds240d(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Różnicówka niemiecka 1 fazowa 40A", catalog)

    assert result.kod is not None and "CDS240D" in result.kod
    assert result.quality == "ok"


def test_opis_bez_podania_fazy_tez_trafia_w_cds240d(db_session, baza_elektryka_json):
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Różnicówka niemiecka 40A", catalog)

    assert result.kod is not None and "CDS240D" in result.kod
    assert result.quality == "ok"


def test_opis_3_fazowy_nadal_trafia_w_osobny_kod_cdc440j(db_session, baza_elektryka_json):
    """Regresja: krotki, ogolny alias na CDS240D nie moze przechwycic jawnie 3-fazowego opisu -
    ten musi nadal trafiac w CDC440J (5-tokenowy alias wygrywa specyficznoscia)."""
    import_catalog(db_session, baza_elektryka_json)
    uzupelnij(db_session)
    catalog = Catalog.from_db(db_session)

    result = match_against_catalog("Różnicówka niemiecka 3 fazowa 40A", catalog)

    assert result.kod is not None and "CDC440J" in result.kod
    assert result.quality == "ok"
