"""
Wzorce atrybutow SPECYFICZNE dla dzialu Hydraulika - gwint, material, zlacze, srednica,
kat, dlugosc, pojemnosc. Analogicznie do parser/core.py (Elektryka), ale osobny slownik
atrybutow branzowych: rury/armatura nie maja kraju/montazu/fazy, za to maja gwint/material.

Zgodne z ekstrakcja uzyta przy budowie tests/fixtures/baza_hydraulika.json.
"""
from __future__ import annotations

import re

COLOR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbia[łl][ayeąę]*\b", re.I), "BIALY"),
    (re.compile(r"\bczarn[ayeąę]*\b", re.I), "CZARNY"),
    (re.compile(r"\bantracyt\w*\b", re.I), "ANTRACYT"),
    (re.compile(r"\bgrafit\w*\b", re.I), "ANTRACYT"),
    (re.compile(r"\bszar[ayeąę]*\b", re.I), "SZARY"),
    (re.compile(r"\bsrebrn[ayeąę]*\b", re.I), "SREBRNY"),
    (re.compile(r"\bbe[żz]ow[ayeąę]*\b", re.I), "BEZOWY"),
    (re.compile(r"\bchrom\w*\b", re.I), "CHROM"),
    (re.compile(r"\bniebiesk[ayeąę]*\b", re.I), "NIEBIESKI"),
]

MATERIAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bPEX\b", re.I), "PEX"),
    (re.compile(r"\bPP\b"), "PP"),
    (re.compile(r"\bPVC\b", re.I), "PVC"),
    (re.compile(r"\bstalow\w*\b", re.I), "STAL"),
    (re.compile(r"\baluminiow\w*\b", re.I), "ALUMINIUM"),
]

FI_RE = re.compile(r"\bFI\s*(\d+(?:[.,]\d+)?)\b", re.I)
ST_RE = re.compile(r"\b(\d+)\s*ST\.?\b", re.I)
CM_RE = re.compile(r"\b(\d+)\s*CM\b", re.I)
L_RE = re.compile(r"\b(\d+)\s*L\b", re.I)
GWINT_RE = re.compile(r"(\d)\s*/\s*(\d)\s*(?:CALA|[\"”])?", re.I)
# NAPRAWA: brak re.I - tekst jest juz zlowercase'owany w core_and_attrs_hydraulika() zanim
# ten wzorzec trafia do niego, wiec bez flagi regex nigdy sie nie dopasowywal (GW/GZ zawsze
# przechodzily do `core` jako nierozpoznany tekst, mimo ze katalog baza_hydraulika.json ma
# poprawnie wyliczone `zlacze` - budowany osobnym procesem offline, nie ta funkcja).
ZLACZE_RE = re.compile(r"\bGW\b|\bGZ\b", re.I)
DN_RE = re.compile(r"\bDN\s*(\d+)\b", re.I)
PN_RE = re.compile(r"\bPN\s*(\d+)\b", re.I)
