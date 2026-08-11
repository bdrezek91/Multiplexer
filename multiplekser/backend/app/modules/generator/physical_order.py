"""FORM_PHYSICAL_ORDER + physical_order_for() - port 1:1 z monolitu.

UWAGA (patrz monolit, komentarz przy FORM_PHYSICAL_ORDER): to NIE jest FORM_ROWS z modulu OCR.
FORM_ROWS (posortowane alfabetycznie) sluzy do dopasowania/poprawiania tekstu odczytu AI
(snap_to_form_row). Ta lista to prawdziwy, FIZYCZNY uklad wierszy na konkretnym formularzu
"Elektryka" (gora->dol, str.1 potem str.3 - str.2/4 sa puste) - uzywana WYLACZNIE do ustalenia
kolejnosci wyniku (sortowanie wykrytych pozycji + wstawianie brakujacych pozycji bazy "pierwsza
wydawka" we wlasciwe miejsce), nigdy do oczyszczania odczytu OCR.

Lista byla juz raz poprawiana po zgloszeniu losowej kolejnosci. Wariant zeskanowany 2026-08-05
(projekt 52/06/26) pokazal, ze realny formularz zawiera jednoczesnie pozycje niemieckie, polskie
i francuskie. Lista ponizej odwzorowuje ten pelny uklad strona po stronie; starsze aliasy pozostaja
obok odpowiadajacych im wierszy. Dzieki temu eksport nie polega na niepewnym fuzzy-matchu przy
ustalaniu kolejnosci.

Wazne: dopasowany kod Optimy moze nazywac sie inaczej niz wiersz formularza (np. "Kinkiet LED
HANA" -> "KINKIET ARCHITEKTONICZNY IP65 CZARNY"). Generator przechowuje pozycje z nazwy
zrodlowej i wedlug niej wstawia elementy "pierwszej wydawki".
"""
from __future__ import annotations

from app.modules.parser.core_elektryka import core_and_attrs
from app.modules.parser.shared import dice_coeff, strip_diacritics
import re

FORM_PHYSICAL_ORDER: list[str] = [
    "Wtyczka odbiornikowa 32A (niebieska) 1F", "Gniazdo przenośne 32A (niebieska) 1F",
    "Wtyczka odbiornikowa 3F 32A", "Gniazdo przenośne 3F 32A",
    "Wtyczka przenośna 3F 32A", "Gniazdo odbiornikowe  3F 32A",
    "Obudowa Hermetyczna na ZUGI", "Złączka szynowa ZUG szara",
    "Złączka szynowa ZUG niebieska", "Złączka szynowa ZUG żółta",
    "Wskaźnik zasilania jednomodułowy (FAZ)", "Rozdzielnica SRN 12 biała",
    "Rozdzielnica SRN 24 biała", "Rozdzielnica SRN 36 biała",
    "Rozdzielnica SRN 48 biała", "Maskownica do rozdzielnicy",
    # Wariant formularza 52/06/26 zawiera obok siebie pozycje niemieckie, polskie i francuskie.
    # Wszystkie musza miec jawna pozycje - fuzzy match nie moze decydowac o kolejnosci eksportu.
    "Rozłącznik izolacyjny modułowy 2P", "Rozłącznik izolacyjny modułowy 4P",
    "Różnicówka niemiecka CDS240D", "Różnicówka niemiecka CDS263D",
    "Różnicówka polska CDC240J", "Różnicówka polska CDA263J",
    "Różnicówka francuska CDS743F", "Różnicówka polska 3 fazowa 40A",
    "Różnicówka niemiecka 3 fazowa 40A",
    "Wyłącznik nadprądowy MBN316E polska 3P 16A", "Wyłącznik nadprądowy MBN325E polska 3P 25A",
    "Wyłącznik nadprądowy MBS 325 niemiecki 3P 25A",
    "Wyłącznik nadprądowy 10A niemiecki", "Wyłącznik nadprądowy 16A niemiecki",
    "Wyłącznik nadprądowy 20A niemiecki", "Wyłącznik nadprądowy 25A niemiecki",
    "Wyłącznik nadprądowy 10A polski", "Wyłącznik nadprądowy 16A polski",
    "Wyłącznik nadprądowy 20A polski", "Wyłącznik nadprądowy 25A polski",
    "Wyłącznik nadprądowy 10A francuski", "Wyłącznik nadprądowy 16A francuski",
    "Gniazdo pojedyńcze niemieckie", "Gniazdo podwójne niemieckie",
    "Gniazdo potrójne niemieckie", "Gniazdo podwójne hermetyczne niemieckie (IP65)",
    "Gniazdo pojedyńcze polskie białe", "Gniazdo podwójne polskie białe",
    "Gniazdo potrójne polskie białe", "Gniazdo podwójne hermetyczne polskie (IP65)",
    "Gniazdo pojedyńcze angielskie", "Gniazdo podwójne angielskie",
    "Gniazdo podłogowe ORNO polskie", "Wyłącznik jednobiegunowy biały",
    "Łącznik świecznikowy biały", "Wyłącznik schodowy biały",
    "Wyłącznik krzyżowy biały", "Oprawa panel LED BLINGO 120X30 biała",
    "Oprawa panel LED BLINGO 60X60 biała", "Szynoprzewód czarny 1mb",
    "Szynoprzewód czarny 2mb", "Lampa LED na szynoprzewód czarna",
    "Szynoprzewód biały 1mb", "Szynoprzewód biały 2mb",
    "Lampa LED na szynoprzewód biała", "Lampa łazienkowa",
    "Lampa łazienkowa hermetyczna biała", "Kinkiet Kanlux LED REKA 7W grafit",
    "Kinkiet LED HANA", "Elektroniczny programator czasowy",
    "Czujnik zmierzchu", "czujka ruchu zewnętrzna",
    "czujka ruchu wewnętrzna", "Grzejnik…...............W",
    "Szyna grzebieniowa widełkowa", "Szyna grzebieniowa trójfazowa",
    "Końcówka tulejkowa  TE 1,5-10", "Końcówka tulejkowa  TE 2,5-10",
    "Końcówka tulejkowa  4-12", "Końcówka tulejkowa  10/12",
    "Końcówka tulejkowa  16/12", "Wago zamykane podwójne",
    "Wago zamykane potrójne", "Wago zamykane 4 przewody", "Wago zamykane 5 przewodów",
    "Przewód 3x1,5", "Przewód 3x2,5",
    "Przewód 3x4", "Przewód 5x4",
    "Przewód 5x16", "Przewód 3X16",
    "Przewód 1x10 kolor", "Przewód OLFLEX 4X1,5",
    "Peszel  Ø.....", "Puszka pusta 86x86",
    "Puszka pusta 86x45", "Puszka czarna Hermetyczna  IP65",
    "Dławica PG….....................", "Korytko 32x15 białe",
    "Korytko 40x25 białe", "Korytko 60x40 białe",
    "Korytko 90x60 białe", "Wkręt ocynk 4,2x16",
    "Wkręt czarny OSB", "INNE", "Gniazdo podtynkowe z klapką grafit",
    "Puszka podtynkowa podwójna", "Ramka podwójna grafit", "Skrzynka LAN",
    "Gniazdo LAN pojed.", "kabel lan",
]


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_diacritics((s or "").lower()))


_PHYSICAL_ORDER_INDEX: dict[str, int] = {_norm_key(n): i for i, n in enumerate(FORM_PHYSICAL_ORDER)}
_FORM_PHYSICAL_CORE: list[str] = [core_and_attrs(n).core for n in FORM_PHYSICAL_ORDER]


def physical_order_for(name: str, fallback: int = 10000) -> int:
    """Zwraca pozycje fizyczna (indeks w FORM_PHYSICAL_ORDER) dla dowolnego tekstu - dokladny
    match po normalizacji, w przeciwnym razie najlepszy fuzzy (Dice) powyzej progu 0.5."""
    key = _norm_key(name)
    if key in _PHYSICAL_ORDER_INDEX:
        return _PHYSICAL_ORDER_INDEX[key]
    q_core = core_and_attrs(name).core
    best, best_r = -1, 0.0
    for idx, cand_core in enumerate(_FORM_PHYSICAL_CORE):
        r = dice_coeff(q_core, cand_core)
        if r > best_r:
            best_r, best = r, idx
    return best if best_r >= 0.5 else fallback
