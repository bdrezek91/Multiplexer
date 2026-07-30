"""FORM_ROWS + snap_to_form_row() - port 1:1 z monolitu (SIATKA KONTROLNA / snapToFormRow()).

Formularz ma zawsze te same wiersze, wiec nazwa zwrocona przez AI musi odpowiadac jednemu z nich.
Dociagamy odczyt do najblizszego wiersza szablonu:
  >= 0.95  -> zgodne, uzywamy nazwy wzorcowej po cichu (status "exact")
  0.70-0.95-> literowka/przekrecona cyfra (np. "60x25" zamiast "40x25"):
              poprawiamy i oznaczamy wiersz do weryfikacji (status "fixed")
  < 0.70   -> nazwa spoza formularza - NIE wchodzi automatycznie, trafia do recznej decyzji (status "off")

UWAGA: to NIE jest FORM_PHYSICAL_ORDER (sortowanie wyniku wg fizycznej kolejnosci kartki) - ta
lista zostaje w module Generator (patrz RAPORT_ETAP_1.md/RAPORT_ETAP_3.md), bo dotyczy porzadku
WYJSCIOWEGO, nie oczyszczania odczytu OCR jak tutaj.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.parser.shared import bigrams, dice_coeff, strip_diacritics

FORM_ROWS: list[str] = [
    'Czujnik zmierzchu',
    'Dławica PG….....................',
    'Elektroniczny programator czasowy',
    'Gniazdo odbiornikowe  3F 32A',
    'Gniazdo podtynkowe z klapką grafit',
    'Gniazdo podwójne angielskie',
    'Gniazdo podwójne hermetyczne angielskie (IP66)',
    'Gniazdo podwójne hermetyczne niemieckie (IP65)',
    'Gniazdo podwójne hermetyczne polskie (IP65)',
    'Gniazdo podwójne niemickie',
    'Gniazdo podwójne niemieckie białe',
    'Gniazdo podwójne niemieckie czarne',
    'Gniazdo podwójne polskie',
    'Gniazdo podwójne polskie białe',
    'Gniazdo podwójne polskie czarne',
    'Gniazdo podłogowe ORNO polskie',
    'Gniazdo pojedyńcze angielskie',
    'Gniazdo pojedyńcze niemieckie',
    'Gniazdo pojedyńcze niemieckie białe',
    'Gniazdo pojedyńcze niemieckie czarne',
    'Gniazdo pojedyńcze polskie',
    'Gniazdo pojedyńcze polskie białe',
    'Gniazdo pojedyńcze polskie czarne',
    'Gniazdo potrójne niemieckie',
    'Gniazdo potrójne niemieckie białe',
    'Gniazdo potrójne niemieckie czarne',
    'Gniazdo potrójne polskie',
    'Gniazdo potrójne polskie białe',
    'Gniazdo potrójne polskie czarne',
    'Gniazdo przenośne 32A (niebieska) 1F',
    'Gniazdo przenośne 3F 32A',
    'Grzejnik…...............W',
    'Kinkiet Kanlux LED REKA 7W grafit',
    'Kinkiet LED HANA',
    'Korytko 32x15',
    'Korytko 32x15 białe',
    'Korytko 32x15 czarne',
    'Korytko 40x25',
    'Korytko 40x25 białe',
    'Korytko 40x25 czarne',
    'Korytko 60x40',
    'Korytko 60x40 białe',
    'Korytko 60x40 czarne',
    'Korytko 90x60',
    'Korytko 90x60 białe',
    'Korytko 90x60 czarne',
    'Końcówka tulejkowa  10/12',
    'Końcówka tulejkowa  16/12',
    'Końcówka tulejkowa  4-12',
    'Końcówka tulejkowa  TE 1,5-10',
    'Końcówka tulejkowa  TE 2,5-10',
    'Lampa LED na szynoprzewód biała',
    'Lampa LED na szynoprzewód czarna',
    'Lampa LED na szynoprzwód biała',
    'Lampa LED na szynoprzwód czarna',
    'Lampa łazienk. hermetyczna czarna z czujnik. ruchu',
    'Lampa łazienkowa',
    'Lampa łazienkowa hermetyczna',
    'Lampa łazienkowa hermetyczna biała',
    'Lampa łazienkowa hermetyczna czarna',
    'Maskownica do rozdzielnicy',
    'Odbudowa Hermetyczna na ZUGI',
    'Oprawa panel LED BLINGO 120X30',
    'Oprawa panel LED BLINGO 120X30 biała',
    'Oprawa panel LED BLINGO 120X30 czarna',
    'Oprawa panel LED BLINGO 60X60',
    'Oprawa panel LED BLINGO 60X60 biała',
    'Oprawa panel LED BLINGO 60X60 czarna',
    'Peszel  Ø.....',
    'Przewód 1x10 kolor',
    'Przewód 3X16',
    'Przewód 3x1,5',
    'Przewód 3x2,5',
    'Przewód 3x4',
    'Przewód 5x16',
    'Przewód 5x4',
    'Przewód OLFLEX 4X1,5',
    'Puszka czarna Hermetyczna  IP65',
    'Puszka pusta 86x45',
    'Puszka pusta 86x86',
    'Puszka pusta 86x86 czarna',
    'Ramka podwójna grafit',
    'Rozdzielnica SRN 12 biała',
    'Rozdzielnica SRN 24',
    'Rozdzielnica SRN 24 biała',
    'Rozdzielnica SRN 24 czarna',
    'Rozdzielnica SRN 36',
    'Rozdzielnica SRN 36 biała',
    'Rozdzielnica SRN 36 czarna',
    'Rozdzielnica SRN 48',
    'Rozdzielnica SRN 48 biała',
    'Rozdzielnica SRN 48 czarna',
    'Rozdzielnica SRN12',
    'Rozdzielnica SRN12 biała',
    'Rozdzielnica SRN12 czarna',
    'Rozdzielnica SRN12 hermetyczna',
    'Rozłącznik izolacyjny modułowy 2P',
    'Rozłącznik izolacyjny modułowy 4P',
    'Róznicówka polska CDC240J',
    'Różnicówka francuska CDS743F',
    'Różnicówka niemiecka 3 fazowa 40A',
    'Różnicówka niemiecka CDS240D',
    'Różnicówka niemiecka CDS263D',
    'Różnicówka polska 3 fazowa 40A',
    'Różnicówka polska CDA263J',
    'Szyna grzebieniowa trójfazowa',
    'Szyna grzebieniowa widełkowa',
    'Szynoprzewód biały 1mb',
    'Szynoprzewód biały 2mb',
    'Szynoprzewód czarny 1mb',
    'Szynoprzewód czarny 2mb',
    'Wago zamykane 4 przewody',
    'Wago zamykane 5 przewodów',
    'Wago zamykane podwójne',
    'Wago zamykane potrójne',
    'Wkręt czarny OSB',
    'Wkręt ocynk 4,2x16',
    'Wskaźnik zasilania jednomodułowy (FAZ)',
    'Wtyczka odbiornikowa 32A (niebieska) 1F',
    'Wtyczka odbiornikowa 3F 32A',
    'Wtyczka przenośna 3F 32A',
    'Wyłącznik jednobiegunowy',
    'Wyłącznik jednobiegunowy biały',
    'Wyłącznik jednobiegunowy czarny',
    'Wyłącznik krzyżowy',
    'Wyłącznik krzyżowy biały',
    'Wyłącznik krzyżowy czarny',
    'Wyłącznik nadprądowy 10A francuski',
    'Wyłącznik nadprądowy 10A niemiecki',
    'Wyłącznik nadprądowy 10A polski',
    'Wyłącznik nadprądowy 16A francuski',
    'Wyłącznik nadprądowy 16A niemiecki',
    'Wyłącznik nadprądowy 16A polski',
    'Wyłącznik nadprądowy 20A niemiecki',
    'Wyłącznik nadprądowy 20A polski',
    'Wyłącznik nadprądowy 25A niemiecki',
    'Wyłącznik nadprądowy 25A polski',
    'Wyłącznik nadprądowy MBN316E polska 3P 16A',
    'Wyłącznik nadprądowy MBN325E polska 3P 25A',
    'Wyłącznik nadprądowy MBS 325 niemiecka 3P 25A',
    'Wyłącznik schodowy',
    'Wyłącznik schodowy biały',
    'Wyłącznik schodowy czarny',
    'Złączka szynowa ZUG niebieska',
    'Złączka szynowa ZUG szara',
    'Złączka szynowa ZUG żółta',
    'czujka ruchu JQ37 zewnętrzna',
    'czujka ruchu wewnętrzna',
    'czujka ruchu zewnętrzna',
    'puszka podtynkowa podwójna',
    'Łącznik świecznikowy',
    'Łącznik świecznikowy biały',
    'Łącznik świecznikowy czarny'
]


def _normalize_key(name: str) -> str:
    stripped = strip_diacritics((name or "").lower())
    cleaned = re.sub(r"[^a-z0-9 ]", " ", stripped)
    return re.sub(r"\s+", " ", cleaned).strip()


_FORM_PARSED = [
    {"name": n, "key": _normalize_key(n), "bg": bigrams(_normalize_key(n))}
    for n in FORM_ROWS
]


@dataclass
class SnapResult:
    name: str
    ratio: float
    status: str  # "exact" | "fixed" | "off"


def snap_to_form_row(name: str) -> SnapResult:
    key = _normalize_key(name)
    if not key:
        return SnapResult(name=name, ratio=0.0, status="off")

    best_name, best_ratio = None, -1.0
    for row in _FORM_PARSED:
        r = dice_coeff(key, row["key"], row["bg"])
        if r > best_ratio:
            best_name, best_ratio = row["name"], r

    if best_name is None:
        return SnapResult(name=name, ratio=0.0, status="off")
    if best_ratio >= 0.95:
        return SnapResult(name=best_name, ratio=best_ratio, status="exact")
    if best_ratio >= 0.70:
        return SnapResult(name=best_name, ratio=best_ratio, status="fixed")
    return SnapResult(name=name, ratio=best_ratio, status="off")


_ATTR_WORD_RE = re.compile(r"\b(podtynkow\w*|natynkow\w*)\b", re.IGNORECASE)
_DIGIT_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _digit_set(s: str) -> set[str]:
    return {d.replace(",", ".") for d in _DIGIT_RE.findall(s)}


@dataclass
class ReconciledName:
    nazwa: str
    form_note: str
    uncertain: bool


def reconcile_form_row(raw: str, snap: SnapResult) -> ReconciledName:
    """Port bug-fixow z runAI() (monolit, ok. linii 1426-1490): snapToFormRow() ma poprawiac
    LITEROWKI OCR (np. "Kortyko" -> "Korytko"), ale przy ratio 0.70-0.95 (status "fixed") nie wolno
    mu przy okazji skasowac REALNYCH roznic (montaz podtynkowy/natynkowy, inne cyfry np. "5x10" vs
    "5x16") - to nie literowki, tylko inny, osobny produkt. Jesli surowy odczyt ma inne
    liczby/slowa atrybutowe niz "poprawiony" wiersz formularza, zachowujemy oryginalny odczyt."""
    nazwa = snap.name
    if snap.status == "fixed":
        words_raw = {w.lower() for w in _ATTR_WORD_RE.findall(raw)}
        words_snap = {w.lower() for w in _ATTR_WORD_RE.findall(snap.name)}
        digits_ok = _digit_set(raw) == _digit_set(snap.name)
        if words_raw != words_snap or not digits_ok:
            nazwa = raw

    # status "fixed" z ODRZUCONA korekta (bo liczby/slowa sie nie zgadzaly) jest ROWNIE niepewny
    # jak status "off" - model tekstowo "prawie" trafil w znany wiersz formularza, ale to co
    # faktycznie zostalo to inny, niesprawdzony produkt (bug wykryty 2026-07-27, "Korytko 60x130").
    uncertain = snap.status == "off" or (snap.status == "fixed" and nazwa == raw and raw != snap.name)

    form_note = ""
    if snap.status == "fixed" and nazwa == snap.name:
        form_note = f'poprawiono z „{raw}" na wiersz formularza — sprawdź'
    elif uncertain:
        form_note = "nazwa spoza formularza — sprawdź, czy dopasowanie poniżej jest poprawne"

    return ReconciledName(nazwa=nazwa, form_note=form_note, uncertain=uncertain)
