"""
Modul Parser - port logiki coreAndAttrs() z monolitu Multiplekser_Elektryka.html.

Odpowiedzialnosc: normalizacja tekstu rozpoznanego przez OCR i ekstrakcja atrybutow
(kraj, kolor, krotnosc, prad, wymiar, przekroj, srednica, biegunowosc, moduly, montaz, faza)
potrzebnych do dopasowania w module Matcher.

Zachowuje 1:1 semantyke oryginalnego JS - patrz docs/ETAP_0_analiza_architektury.md pkt 2.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

# ---- Wzorce atrybutow (odpowiednik COUNTRY_PATTERNS / COLOR_PATTERNS / MULT_PATTERNS w JS) ----

COUNTRY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bniemiec\w*\b", re.I), "DE"),
    (re.compile(r"\bpolsk\w*\b", re.I), "PL"),
    (re.compile(r"\bfrancus\w*\b", re.I), "FR"),
    (re.compile(r"\bangiels\w*\b", re.I), "EN"),
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
DIM_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+)")
WIRE_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+(?:[.,]\d+)?)")
SREDNICA_RE = re.compile(r"\bfi\s*(\d+(?:[.,]\d+)?)\b|\bpg\s*-?\s*(\d+(?:[.,]\d+)?)\b", re.I)
BIEGUN_RE = re.compile(r"\b(\d)\s*p\b", re.I)
MODULOW_KEYWORDS_RE = re.compile(r"\b(rozdzielnic\w*|rh|srn)\b", re.I)
ATTR_WORD_RE = re.compile(r"\b(podtynkow\w*|natynkow\w*)\b", re.I)

SYNONYMS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbezpiecznik\b", re.I), "wylacznik nadpradowy"),
    (re.compile(r"\bkabel\w*\b", re.I), "przewod"),
]


def strip_diacritics(s: str) -> str:
    """Usuwa polskie znaki diakrytyczne (odpowiednik stripDiacritics() w JS)."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").replace("ł", "l").replace("Ł", "L")


def _extract(text: str, patterns: list[tuple[re.Pattern, str]]) -> tuple[Optional[str], str]:
    """Zwraca (wartosc, tekst_po_usunieciu_dopasowania) - odpowiednik extractAttr()."""
    for pattern, value in patterns:
        m = pattern.search(text)
        if m:
            return value, pattern.sub(" ", text)
    return None, text


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


PHASE_1F_RE = re.compile(r"\b1\s*f(az\w*)?\b|\bjednofazow\w*\b", re.I)
PHASE_3F_RE = re.compile(r"\b3\s*f(az\w*)?\b|\btr[oó]jfazow\w*\b|\b3p\s*\+?\s*n?\s*\+?\s*pe\b", re.I)


def detect_phase(original_text: str) -> Optional[str]:
    if PHASE_3F_RE.search(original_text):
        return "3F"
    if PHASE_1F_RE.search(original_text):
        return "1F"
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

    # Montaz (podtynkowy/natynkowy) - wykrywane PRZED reszta obrobki, zeby nie zniknelo w core.
    montaz = None
    if re.search(r"\bpodtynkow\w*\b", t, re.I):
        montaz = "PODTYNKOWY"
        t = re.sub(r"\bpodtynkow\w*\b", " ", t, flags=re.I)
    elif re.search(r"\bnatynkow\w*\b", t, re.I):
        montaz = "NATYNKOWY"
        t = re.sub(r"\bnatynkow\w*\b", " ", t, flags=re.I)

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
