"""Walidacja danych edytowanych recznie przed generowaniem pliku do Optimy."""
import math

import pytest
from pydantic import ValidationError

from app.modules.documents.schemas import DocumentItemAddIn, DocumentItemUpdateIn


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf, -math.inf])
def test_dodanie_pozycji_odrzuca_nieprawidlowa_ilosc(value):
    with pytest.raises(ValidationError):
        DocumentItemAddIn(match_kod="TEST", ilosc_finalna=value)


@pytest.mark.parametrize("value", [0, -1, math.nan, math.inf, -math.inf])
def test_edycja_pozycji_odrzuca_nieprawidlowa_ilosc(value):
    with pytest.raises(ValidationError):
        DocumentItemUpdateIn(ilosc_finalna=value)


def test_edycja_pozycji_nadal_pozwala_wykluczyc_ja_przez_null():
    assert DocumentItemUpdateIn(ilosc_finalna=None).ilosc_finalna is None
