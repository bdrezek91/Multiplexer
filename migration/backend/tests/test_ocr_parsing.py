"""Testy Etapu 6: extract_json()/validate_item() - port extractJSON()/validAIItem() z monolitu."""
from app.modules.ocr.parsing import extract_json, validate_item


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
