"""
Modul Parser (Elektryka) - port logiki coreAndAttrs() z monolitu Multiplekser_Elektryka.html.

Odpowiedzialnosc: normalizacja tekstu rozpoznanego przez OCR i ekstrakcja atrybutow
(kraj, kolor, krotnosc, prad, wymiar, przekroj, srednica, biegunowosc, moduly, montaz, faza)
potrzebnych do dopasowania w module Matcher.

Zachowuje 1:1 semantyke oryginalnego JS - patrz docs/ETAP_0_analiza_architektury.md pkt 2.

Nazwa pliku (dawniej core.py, patrz docs/RAPORT_NAZEWNICTWO_1.md) - jedyna logika specyficzna
dla Elektryki, dolna warstwa (strip_diacritics/bigrams/dice_coeff/DIM_RE) jest w shared.py,
bo Hydraulika (parser/hydraulika.py) tez jej uzywa."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .shared import DIM_RE, strip_diacritics

# ---- Wzorce atrybutow (odpowiednik COUNTRY_PATTERNS / COLOR_PATTERNS / MULT_PATTERNS w JS) ----

COUNTRY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(polski[ea]?|polska)\b", re.I), "PL"),
    # DE: obok "niemiecki(e)/niemiecka" takze warianty tolerancyjne na literowki OCR
    # ("niemicki/niemicka" - brak 'e', "niemieki/niemieka" - brak 'c') - port 1:1 z monolitu.
    (re.compile(r"\b(niemiecki[ea]?|niemiecka|niemicki[ea]?|niemicka|niemieki[ea]?|niemieka)\b", re.I), "DE"),
    (re.compile(r"\b(francuski[ea]?|francuska)\b", re.I), "FR"),
    (re.compile(r"\b(angielski[ea]?|angielska)\b", re.I), "EN"),
    # Same skroty (np. z Excela/OCR skrotowego zapisu) - brakowaly w tym porcie.
    (re.compile(r"\bPL\b", re.I), "PL"),
    (re.compile(r"\bDE\b", re.I), "DE"),
    (re.compile(r"\bFR\b", re.I), "FR"),
    (re.compile(r"\bEN\b", re.I), "EN"),
]

# NAPRAWA (bug wykryty 2026-07-27): brakowalo 5 z 10 kolorow realnie obecnych w katalogu -
# powodowalo falszywy konflikt z domyslnym "bialy" dla kazdego produktu w tych kolorach
# (np. "WTYCZKA ODBIORNIKOWA 16A NIEBIESKA").
COLOR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbia[łl](y|a|e|ego)\b", re.I), "biały"),
    (re.compile(r"\bczarn(y|a|e|ego)\b", re.I), "czarny"),
    (re.compile(r"\bgrafit\w*\b", re.I), "grafit"),
    (re.compile(r"\bantracyt\w*\b", re.I), "antracyt"),
    (re.compile(r"\bszar(y|a|e|ego)\b", re.I), "szary"),
    (re.compile(r"\bniebiesk(i|a|ie|iego)\b", re.I), "niebieski"),
    (re.compile(r"\bczerwon(y|a|e|ego)\b", re.I), "czerwony"),
    (re.compile(r"\bż[óo][łl]t(y|a|e|ego)\b", re.I), "żółty"),
    (re.compile(r"\bzielon(y|a|e|ego)\b", re.I), "zielony"),
    (re.compile(r"\btransparentn(y|a|e|ego)\b|\bprzezroczyst(y|a|e|ego)\b", re.I), "transparentny"),
]

MULT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bpojedy[nń]?cze\b|\bpojedynczy\b", re.I), "1"),
    (re.compile(r"\bpodw[oó]jne\b|\bpodw[oó]jny\b", re.I), "2"),
    (re.compile(r"\bpotr[oó]jne\b|\bpotr[oó]jny\b", re.I), "3"),
    (re.compile(r"\bpoczw[oó]rne\b|\bpoczw[oó]rny\b", re.I), "4"),
]

AMP_RE = re.compile(r"(\d+)\s*A\b", re.I)
WIRE_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)")
SREDNICA_RE = re.compile(r"\bfi\s*(\d+(?:[.,]\d+)?)\b|\bpg\s*-?\s*(\d+(?:[.,]\d+)?)\b", re.I)
BIEGUN_RE = re.compile(r"\b(\d)\s*p\b", re.I)
MODULOW_KEYWORDS_RE = re.compile(r"\b(rozdzielnic\w*|rh|srn)\b", re.I)
ATTR_WORD_RE = re.compile(r"\b(podtynkow\w*|natynkow\w*)\b", re.I)

SYNONYMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbezpiecznik\b", re.I), "wylacznik nadpradowy"),
    (re.compile(r"\bkabel\w*\b", re.I), "przewod"),
]


def _extract(text: str, patterns: list[tuple[re.Pattern, str]]) -> tuple[Optional[str], str]:
    """Zwraca (wartosc, tekst_po_usunieciu_dopasowania) - odpowiednik extractAttr()."""
    for pattern, value in patterns:
        m = pattern.search(text)
        if m:
            return value, pattern.sub(" ", text)
    return None, text


# Pelna detekcja fazy (port 1:1 z detectPhase() w monolicie - wersja Excel): napiecia
# (230V=1F, 400V=3F), zapisy biegunow (2P+PE=1F, 3P+N+PE/5P=3F), slownie (jednofazowe/
# trojfazowe), skroty (1F/3F) oraz heurystyka kolorow CEE dla osprzetu silowego:
# niebieskie=1F, czerwone=3F (tylko w kontekscie gniazd/wtyczek - patrz _CEE_CONTEXT_RE).
_PHASE_1F_PATTERNS = [
    re.compile(r"\b1f\b"),
    re.compile(r"\b1\s*f\b"),
    re.compile(r"\b1-fazowe?\b"),
    re.compile(r"\b1\s*-\s*fazowe?\b"),
    re.compile(r"\bjednofazow[aei]\b"),
    re.compile(r"\b230v\b"),
    re.compile(r"\b230\s*v\b"),
    re.compile(r"\b2p\s*\+\s*pe\b"),
    re.compile(r"\b2p\+pe\b"),
]
_PHASE_3F_PATTERNS = [
    re.compile(r"\b3f\b"),
    re.compile(r"\b3\s*f\b"),
    re.compile(r"\b3-fazowe?\b"),
    re.compile(r"\b3\s*-\s*fazowe?\b"),
    re.compile(r"\btr[oó]jfazow[aei]\b"),
    re.compile(r"\b400v\b"),
    re.compile(r"\b400\s*v\b"),
    re.compile(r"\b3p\s*\+\s*n\s*\+\s*pe\b"),
    re.compile(r"\b3p\+n\+pe\b"),
    re.compile(r"\b5p\b"),
]
_CEE_CONTEXT_RE = re.compile(r"\b(gniazdo|wtyczka|wtyk|odbiornik|przenośn[ay]|stał[ay]|cee|złączka|gniazdko)\b", re.I)


def detect_phase(original_text: str) -> Optional[str]:
    s = original_text.lower()
    for pattern in _PHASE_1F_PATTERNS:
        if pattern.search(s):
            return "1F"
    for pattern in _PHASE_3F_PATTERNS:
        if pattern.search(s):
            return "3F"
    if _CEE_CONTEXT_RE.search(s):
        if re.search(r"\bniebiesk[ai]\b", s):
            return "1F"
        if re.search(r"\bblue\b", s):
            return "1F"
        if re.search(r"\bczerwon[ae]\b", s):
            return "3F"
        if re.search(r"\bred\b", s):
            return "3F"
    return None


@dataclass
class ParsedAttrs:
    core: str
    country: Optional[str] = None
    color: Optional[str] = None
    mult: Optional[str] = None
    amp: Optional[str] = None
    dim: Optional[str] = None
    phase: Optional[str] = None
    zyl: Optional[int] = None
    przekroj: Optional[float] = None
    srednica: Optional[float] = None
    biegunow: Optional[int] = None
    modulow: Optional[int] = None
    montaz: Optional[str] = None


_WIRE_CONTEXT_RE = re.compile(r"\bprzew[oó]d\w*\b|\bkabel\w*\b|\bolflex\b|\bsterownicz\w*\b", re.I)


def core_and_attrs(name: str) -> ParsedAttrs:
    """Port 1:1 funkcji coreAndAttrs() z JS. Patrz monolit dla pelnej historii poprawek."""
    original = name
    t = name.lower()

    # NAPRAWA (bug wykryty 2026-07-27): tylko usuwamy same znaki nawiasu (rozpakowujemy),
    # tresc zostaje w strumieniu tekstu - kolor/kraj/montaz w nawiasach musza nadal byc wykryte.
    t = re.sub(r"[()]", " ", t)

    # OCR czesto skleja slowa bez spacji - wstawiamy spacje przed typowymi granicami.
    t = re.sub(r"(\d+\s*a?)(niemiec|niemiek|polsk|francus|angiels)", r"\1 \2", t, flags=re.I)
    t = re.sub(
        r"(niemiecki|niemiecka|polski|polska|francuski|francuska|angielski|angielska)"
        r"(biał|czarn|szar|grafit|antracyt)",
        r"\1 \2", t, flags=re.I,
    )

    for pattern, repl in SYNONYMS:
        t = pattern.sub(repl, t)

    country, t = _extract(t, COUNTRY_PATTERNS)
    color, t = _extract(t, COLOR_PATTERNS)
    mult, t = _extract(t, MULT_PATTERNS)

    # Montaz - wykrywany PRZED reszta obrobki, zeby nie zniknal w core. W osprzecie CEE
    # "gniazdo odbiornikowe" oznacza gniazdo stale, a nie domowe gniazdo podtynkowe.
    montaz = None
    if re.search(r"\bpodtynkow\w*\b", t, re.I):
        montaz = "PODTYNKOWY"
        t = re.sub(r"\bpodtynkow\w*\b", " ", t, flags=re.I)
    elif re.search(r"\bnatynkow\w*\b", t, re.I):
        montaz = "NATYNKOWY"
        t = re.sub(r"\bnatynkow\w*\b", " ", t, flags=re.I)
    elif re.search(r"\bgniazd\w*\b.*\b(odbiornikow\w*|sta[łl]\w*)\b", t, re.I):
        montaz = "STALY"

    amp_m = AMP_RE.search(t)
    amp = amp_m.group(1) if amp_m else None
    if amp_m:
        t = AMP_RE.sub(" ", t)

    # Przewod: "3x1,5"/"5x10" -> liczba_zyl x przekroj_mm2, tylko w kontekscie przewodow/kabli.
    zyl: Optional[int] = None
    przekroj: Optional[float] = None
    if _WIRE_CONTEXT_RE.search(t):
        wm = WIRE_RE.search(t)
        if wm:
            zyl = int(wm.group(1))
            przekroj = float(wm.group(2).replace(",", "."))
            t = WIRE_RE.sub(" ", t)

    srednica: Optional[float] = None
    sr_m = SREDNICA_RE.search(t)
    if sr_m:
        raw = sr_m.group(1) or sr_m.group(2)
        srednica = float(raw.replace(",", "."))
        t = SREDNICA_RE.sub(" ", t)

    biegunow: Optional[int] = None
    bg_m = BIEGUN_RE.search(t)
    if bg_m:
        biegunow = int(bg_m.group(1))
        t = BIEGUN_RE.sub(" ", t)

    modulow: Optional[int] = None
    if MODULOW_KEYWORDS_RE.search(t):
        mm = re.search(r"\b(\d{1,3})\b", t)
        if mm:
            modulow = int(mm.group(1))
            t = t.replace(mm.group(0), " ", 1)

    dim: Optional[str] = None
    dim_m = DIM_RE.search(t)
    if dim_m:
        dim = "x".join(sorted([dim_m.group(1), dim_m.group(2)]))
        t = DIM_RE.sub(" ", t)

    phase = detect_phase(original)

    t = strip_diacritics(t).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    return ParsedAttrs(
        core=t, country=country, color=color, mult=mult, amp=amp, dim=dim, phase=phase,
        zyl=zyl, przekroj=przekroj, srednica=srednica, biegunow=biegunow, modulow=modulow,
        montaz=montaz,
    )
