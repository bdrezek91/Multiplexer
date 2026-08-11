"""Testy Etapu 6: extract_json()/validate_item() - port extractJSON()/validAIItem() z monolitu."""
from app.modules.ocr.parsing import extract_json, is_actionable_item, validate_item


def test_extract_json_czysty_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_owiniety_markdownem():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_z_tekstem_wokol():
    assert extract_json('Oto wynik: {"pozycje": [1, 2]} dziekuje') == {"pozycje": [1, 2]}


def test_extract_json_tablica():
    assert extract_json('[{"nazwa": "X"}]') == [{"nazwa": "X"}]


def test_extract_json_niesparsowalny_tekst_zwraca_none():
    assert extract_json("to nie jest json") is None


def test_extract_json_pusty_tekst_zwraca_none():
    assert extract_json("") is None
    assert extract_json(None) is None


def test_validate_item_poprawny():
    assert validate_item({"nazwa": "Grzejnik", "ilosc_wydana": "2", "ilosc_zuzyta": None}) is True


def test_validate_item_zbyt_krotka_nazwa():
    assert validate_item({"nazwa": "X"}) is False


def test_validate_item_brak_nazwy():
    assert validate_item({"ilosc_wydana": "2"}) is False


def test_validate_item_nienumeryczna_ilosc():
    assert validate_item({"nazwa": "Grzejnik", "ilosc_wydana": "abc"}) is False


def test_validate_item_ilosc_z_jednostka_akceptowana_tak_jak_w_js():
    """JS parseFloat('5 szt') == 5 (nie NaN) - port musi byc tak samo tolerancyjny."""
    assert validate_item({"nazwa": "Grzejnik", "ilosc_wydana": "5 szt"}) is True


def test_validate_item_nie_dict():
    assert validate_item("napis") is False
    assert validate_item(None) is False


def test_pusty_wiersz_szablonu_nie_jest_pozycja_do_kontroli():
    assert is_actionable_item({
        "nazwa": "Rozdzielnica SRN 36 biala",
        "ilosc_wydana": None,
        "ilosc_zuzyta": None,
    }) is False


def test_nieczytelny_wiersz_z_widocznym_oznaczeniem_jest_do_kontroli():
    assert is_actionable_item({
        "nazwa": "Rozdzielnica SRN 36 biala",
        "ilosc_wydana": None,
        "ilosc_zuzyta": None,
        "ma_oznaczenie": True,
    }) is True


def test_odczytana_ilosc_jest_pozycja_nawet_bez_flagi_oznaczenia():
    assert is_actionable_item({
        "nazwa": "Rozdzielnica SRN 12 biala",
        "ilosc_wydana": 1,
        "ilosc_zuzyta": None,
    }) is True
