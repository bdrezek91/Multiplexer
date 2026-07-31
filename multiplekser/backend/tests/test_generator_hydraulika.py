"""
Testy modulu Generator dla Hydrauliki - port generateOutput() z Multipekser_Hydraulika.html.
Kazdy przypadek weryfikuje jedna udokumentowana zasade z komentarza nad generateOutput() w
zrodle (patrz generator/core_hydraulika.py, docstring).
"""
import json
from pathlib import Path

import pytest

from app.modules.generator import GeneratorItem, generate_output_hydraulika
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_hydraulika.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db, dzial="hydraulika")


def test_dopasowana_pozycja_trafia_do_wyniku(catalog):
    items = [GeneratorItem(name="Bojler 80 L", qty=2)]
    result = generate_output_hydraulika(items, catalog, magazyn="Zabrze")
    assert result.lines == ["BOJLER 80 L;2;;SZT;Zabrze"]


def test_kolejnosc_wyniku_to_kolejnosc_wejscia_nie_fizyczna(catalog):
    """Hydraulika NIE sortuje wg fizycznego ukladu formularza (w przeciwienstwie do Elektryki) -
    kolejnosc wyniku = kolejnosc pozycji w dokumencie zrodlowym."""
    items = [
        GeneratorItem(name="Bojler 80 L", qty=1),
        GeneratorItem(name="Zawór kątowy 1/2x3/4", qty=1),
    ]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    kody = [line.split(";")[0] for line in result.lines]
    assert kody == ["BOJLER 80 L", "ZAWÓR KĄTOWY 1/2X3/4"]


def test_duplikaty_scalane_w_miejscu_pierwszego_wystapienia(catalog):
    items = [
        GeneratorItem(name="Bojler 80 L", qty=1),
        GeneratorItem(name="Zawór kątowy 1/2x3/4", qty=1),
        GeneratorItem(name="Bojler 80 L", qty=3),
    ]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    kody = [line.split(";")[0] for line in result.lines]
    assert kody == ["BOJLER 80 L", "ZAWÓR KĄTOWY 1/2X3/4"]  # nie 3 linie
    assert result.lines[0] == "BOJLER 80 L;4;;SZT;"  # 1 + 3 scalone


def test_brak_dopasowania_generuje_komentarz_z_podpowiedzia(catalog):
    items = [GeneratorItem(name="Calkowicie nieznana pozycja xyz123", qty=1)]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    assert len(result.lines) == 1
    assert result.lines[0].startswith("### BRAK DOPASOWANIA")


def test_brak_always_include_pierwsza_wydawka(catalog):
    """Hydraulika nie ma odpowiednika 'pierwsza wydawka' - funkcja nie przyjmuje w ogole
    takiego parametru (w przeciwienstwie do generate_output() dla Elektryki)."""
    import inspect
    from app.modules.generator import generate_output_hydraulika as fn
    assert "first_wydawka" not in inspect.signature(fn).parameters


def test_tryb_wszystko_po_1_szt(catalog):
    items = [GeneratorItem(name="Bojler 80 L", qty=5)]
    result = generate_output_hydraulika(items, catalog, magazyn=None, qty_mode="ones")
    assert result.lines == ["BOJLER 80 L;1;;SZT;"]


def test_ostrzezenie_brak_magazynu(catalog):
    items = [GeneratorItem(name="Bojler 80 L", qty=1)]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    assert result.warning_no_magazyn is True

    result2 = generate_output_hydraulika(items, catalog, magazyn="Zabrze")
    assert result2.warning_no_magazyn is False


def test_pusta_lista_pozycji(catalog):
    result = generate_output_hydraulika([], catalog, magazyn=None)
    assert result.lines == []
    assert result.warning_no_magazyn is False


# ---- Reczna korekta dopasowania (2026-07-31) ----

def test_generate_output_hydraulika_uzywa_zapisanego_dopasowania_gdy_ok(catalog):
    """Ten sam realny blad co w Elektryce (patrz test_generator.py) - generator ignorowal
    reczna korekte match_kod i dopasowywal surowa nazwe od zera."""
    items = [GeneratorItem(
        name="cos niejasnego xyz", qty=2, match_kod="BOJLER 80 L", match_nazwa="Bojler 80 L",
        match_jm="SZT", match_quality="ok",
    )]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    assert result.lines == ["BOJLER 80 L;2;;SZT;"]


def test_generate_output_hydraulika_ignoruje_zapisane_dopasowanie_gdy_nie_ok(catalog):
    items = [GeneratorItem(name="Bojler 80 L", qty=1, match_kod="ZAWÓR KĄTOWY 1/2X3/4", match_quality="bad")]
    result = generate_output_hydraulika(items, catalog, magazyn=None)
    assert result.lines == ["BOJLER 80 L;1;;SZT;"]
