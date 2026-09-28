"""Testy diagnose_candidate_elektryka() - warstwa diagnostyczna dla Jev shadow (Etap 3,
2026-09-29). Nie testuje match_against_catalog() (ten ma wlasna, nietykana suite w
test_matcher.py) - tylko sygnaly per-atrybut dla pojedynczego kandydata."""
import json
from pathlib import Path

import pytest

from app.modules.matcher.candidate_diagnostics import diagnose_candidate_elektryka
from app.modules.parser.core_elektryka import core_and_attrs
from app.modules.products import Catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    db = json.loads((FIXTURES / "baza_elektryka.json").read_text(encoding="utf-8"))
    return Catalog.from_json_dict(db)


def _product(catalog: Catalog, kod: str):
    for p in catalog.products:
        if p.kod == kod:
            return p
    raise AssertionError(f"Brak produktu {kod!r} w fixture")


def test_cds240d_ma_brakujacy_prad_i_faze_ale_zgodny_kraj(catalog):
    """Realny przypadek z raportu Jev: CDS240D ma standard_gniazda=DE (zgodny), ale
    prad_A=None i liczba_faz=None w katalogu - wiec Jev "nie ma skad wiedziec" ze to
    dokladnie 1-fazowa 40A, poza semantyka nazwy. Diagnostyka ma to pokazac jako missing,
    NIE jako conflict (bo katalog po prostu nie ma tej wartosci, nie ma innej)."""
    q = core_and_attrs("Różnicówka niemiecka 1 fazowa 40A")
    cand = _product(catalog, "RÓŻNICÓWKA NIEMIECKA CDS240D")

    diag = diagnose_candidate_elektryka(q, cand)

    assert diag.country.match is True
    assert diag.country.conflict is False


def test_wyraznie_zly_kraj_to_konflikt(catalog):
    q = core_and_attrs("Różnicówka francuska 1 fazowa 40A")
    cand = _product(catalog, "RÓŻNICÓWKA NIEMIECKA CDS240D")

    diag = diagnose_candidate_elektryka(q, cand)

    assert diag.country.conflict is True
    assert diag.country.match is False


def test_brak_atrybutu_w_zapytaniu_nie_generuje_sygnalu(catalog):
    """Jesli zapytanie nie podaje amperazu, nie oceniamy tego atrybutu wcale (ani match,
    ani conflict, ani missing) - brak informacji w zapytaniu, nie brak w katalogu."""
    q = core_and_attrs("Różnicówka niemiecka")
    cand = _product(catalog, "RÓŻNICÓWKA NIEMIECKA CDS240D")

    diag = diagnose_candidate_elektryka(q, cand)

    assert diag.amp.match is False
    assert diag.amp.conflict is False
    assert diag.amp.missing is False


def test_as_dict_ma_wszystkie_oczekiwane_klucze(catalog):
    q = core_and_attrs("Różnicówka niemiecka 1 fazowa 40A")
    cand = _product(catalog, "RÓŻNICÓWKA NIEMIECKA CDS240D")

    d = diagnose_candidate_elektryka(q, cand).as_dict()

    for prefix in ("country", "amp", "phase", "dim", "przekroj", "zyl", "biegunow", "modulow", "srednica"):
        assert f"{prefix}_match" in d
        assert f"{prefix}_conflict" in d
        assert f"{prefix}_missing" in d
    assert "color_match" in d
    assert "montaz_conflict" in d
