"""Dolna warstwa Parsera - naprawde wspolna miedzy dzialami (uzywana wprost przez
parser/hydraulika.py, matcher/special_rules.py, products/catalog.py, ocr/form_rows_elektryka.py
i ocr/form_rows_hydraulika.py), wydzielona z dawnego core.py (patrz docs/RAPORT_NAZEWNICTWO_1.md).

Nie zawiera niczego specyficznego dla Elektryki - `DIM_RE` jest tu mimo pochodzenia z sekcji
wzorcow atrybutow Elektryki, bo Hydraulika tez go uzywa (patrz parser/hydraulika.py, komentarz
"Wspolna zostaje tylko dolna warstwa")."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

DIM_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+)")


def strip_diacritics(s: str) -> str:
    """Usuwa polskie znaki diakrytyczne (odpowiednik stripDiacritics() w JS)."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").replace("ł", "l").replace("Ł", "L")


def bigrams(s: str) -> list[str]:
    s = s.replace(" ", "")
    return [s[i:i + 2] for i in range(len(s) - 1)] if len(s) >= 2 else []


def dice_coeff(a: str, b: str, b_bigrams: Optional[list[str]] = None) -> float:
    if a == b:
        return 1.0
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0
    ga = bigrams(a)
    gb = list(b_bigrams if b_bigrams is not None else bigrams(b))
    matches = 0
    for g in ga:
        if g in gb:
            matches += 1
            gb.remove(g)
    return (2 * matches) / (len(ga) + len(b_bigrams if b_bigrams is not None else bigrams(b)))
