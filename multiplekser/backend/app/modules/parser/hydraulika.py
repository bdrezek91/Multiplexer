"""
Modul Parser dla dzialu Hydraulika. Osobna funkcja i osobny dataclass od Elektryki
(core.py) - SWIADOMA decyzja (nie przeoczenie): pola atrybutow Hydrauliki (gwint/
material/zlacze) sa fundamentalnie inne od Elektryki (kraj/kolor/montaz/faza), wiec
wspolny dataclass z polami obu dzialow na krzyz bylby mylacy (puste pola nalezace do
innego dzialu). Wspolna zostaje tylko dolna warstwa (strip_diacritics/DIM_RE z core.py).

Jesli w przyszlosci (3. dzial) ten wzorzec "kopiuj plik, zmien pola" zacznie byc
uciazliwy - do rozwazenia ujednolicenie do jednego generycznego ParsedAttrs z workiem
`extra: dict` (YAGNI: nie budujemy tego teraz, dopoki nie ma trzeciej, realnej potrzeby).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.modules.parser import hydraulika_patterns as hp
from app.modules.parser.shared import DIM_RE, strip_diacritics


def _extract(text: str, patterns: list[tuple[re.Pattern, str]]) -> tuple[Optional[str], str]:
    """Zwraca (wartosc, tekst_po_usunieciu_dopasowania) - pierwszy pasujacy wzorzec wygrywa.
    Identyczna logika co prywatne `_extract` w parser/core.py - zduplikowana zamiast
    importowana (4 linie, nie warto jeszcze wydzielac wspolnego modulu, patrz YAGNI wyzej)."""
    for pattern, value in patterns:
        m = pattern.search(text)
        if m:
            return value, pattern.sub(" ", text)
    return None, text


@dataclass
class ParsedAttrsHydraulika:
    core: str
    kolor: Optional[str] = None
    material: Optional[str] = None
    zlacze: Optional[str] = None
    srednica_mm: Optional[float] = None
    kat_st: Optional[int] = None
    gwint_cal: Optional[str] = None
    dlugosc_cm: Optional[int] = None
    pojemnosc_l: Optional[int] = None
    wymiar_mm: Optional[str] = None


def core_and_attrs_hydraulika(name: str) -> ParsedAttrsHydraulika:
    """Ekstrakcja atrybutow dla zapytan z dzialu Hydraulika - zgodna z logika uzyta przy
    budowie tests/fixtures/baza_hydraulika.json (ten sam zestaw wzorcow)."""
    t = name.lower()
    t = re.sub(r"[()]", " ", t)

    kolor, t = _extract(t, hp.COLOR_PATTERNS)
    material, t = _extract(t, hp.MATERIAL_PATTERNS)

    zlacze = None
    m = hp.ZLACZE_RE.search(t)
    if m:
        zlacze = m.group(0).upper()
        t = hp.ZLACZE_RE.sub(" ", t)

    srednica = None
    m = hp.FI_RE.search(t)
    if m:
        srednica = float(m.group(1).replace(",", "."))
        t = hp.FI_RE.sub(" ", t)

    kat_st = None
    m = hp.ST_RE.search(t)
    if m:
        kat_st = int(m.group(1))
        t = hp.ST_RE.sub(" ", t)

    gwint_matches_t = list(hp.GWINT_RE.finditer(t))
    gwint_cal = None
    if gwint_matches_t:
        vals = ["/".join(g.groups()) for g in gwint_matches_t]
        gwint_cal = "x".join(vals) if len(vals) > 1 else vals[0]
        t = hp.GWINT_RE.sub(" ", t)

    dlugosc_cm = None
    m = hp.CM_RE.search(t)
    if m:
        dlugosc_cm = int(m.group(1))
        t = hp.CM_RE.sub(" ", t)

    pojemnosc_l = None
    m = hp.L_RE.search(t)
    if m:
        pojemnosc_l = int(m.group(1))
        t = hp.L_RE.sub(" ", t)

    wymiar_mm = None
    dim_m = DIM_RE.search(t)
    if dim_m and not gwint_cal:
        wymiar_mm = "x".join(sorted([dim_m.group(1), dim_m.group(2)]))
        t = DIM_RE.sub(" ", t)

    t = strip_diacritics(t).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    return ParsedAttrsHydraulika(
        core=t, kolor=kolor, material=material, zlacze=zlacze, srednica_mm=srednica,
        kat_st=kat_st, gwint_cal=gwint_cal, dlugosc_cm=dlugosc_cm, pojemnosc_l=pojemnosc_l,
        wymiar_mm=wymiar_mm,
    )
