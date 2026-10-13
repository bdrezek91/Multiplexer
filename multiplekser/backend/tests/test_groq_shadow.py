from types import SimpleNamespace

from app.modules.documents.groq_shadow import _compare_shadow


def _shadow(name, wyd=None, zuz=None):
    return SimpleNamespace(
        rozpoznana_nazwa=name,
        ilosc_wydana=wyd,
        ilosc_zuzyta=zuz,
    )


def test_compare_shadow_liczy_zgodne_i_rozne_ilosci():
    main = [
        {"rozpoznana_nazwa": "Kompakt WC", "ilosc_wydana": 1, "ilosc_zuzyta": 1},
        {"rozpoznana_nazwa": "Trójnik PP 20", "ilosc_wydana": None, "ilosc_zuzyta": 3},
        {"rozpoznana_nazwa": "Rura PP fi 20", "ilosc_wydana": 11, "ilosc_zuzyta": 10},
    ]
    shadow = [
        _shadow("Kompakt WC", 1, 1),
        _shadow("Trójnik PP 20", 3, None),
        _shadow("Nowa pozycja", 2, 2),
    ]

    result = _compare_shadow(main, shadow)
    assert result["matched"] == 2
    assert result["exact_qty"] == 1
    assert result["mismatch_count"] == 1
    assert result["main_only_count"] == 1
    assert result["shadow_only_count"] == 1
