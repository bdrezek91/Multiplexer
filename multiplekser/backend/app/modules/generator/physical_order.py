"""FORM_PHYSICAL_ORDER + physical_order_for() - port 1:1 z monolitu.

UWAGA (patrz monolit, komentarz przy FORM_PHYSICAL_ORDER): to NIE jest FORM_ROWS z modulu OCR.
FORM_ROWS (posortowane alfabetycznie) sluzy do dopasowania/poprawiania tekstu odczytu AI
(snap_to_form_row). Ta lista to prawdziwy, FIZYCZNY uklad wierszy na konkretnym formularzu
"Elektryka" (gora->dol, str.1 potem str.2) - uzywana WYLACZNIE do ustalenia kolejnosci wyniku
(sortowanie wykrytych pozycji + wstawianie brakujacych pozycji bazy "pierwsza wydawka" we
wlasciwe miejsce), nigdy do oczyszczania odczytu OCR.
"""
from __future__ import annotations

from app.modules.parser.core_elektryka import core_and_attrs
from app.modules.parser.shared import dice_coeff, strip_diacritics
import re

FORM_PHYSICAL_ORDER: list[str] = [
    "Wtyczka odbiornikowa 32A (niebieska) 1F", "Gniazdo przenośne 32A (niebieska) 1F",
    "Wtyczka odbiornikowa 3F 32A", "Gniazdo przenośne 3F 32A",
    "Wtyczka przenośna 3F 32A", "Gniazdo odbiornikowe  3F 32A",
    "Rozdzielnica SRN12", "Rozdzielnica SRN 24",
    "Rozdzielnica SRN 36", "Rozdzielnica SRN 48",
    "Maskownica do rozdzielnicy", "Rozłącznik izolacyjny modułowy 2P",
    "Różnicówka niemiecka CDS240D", "Różnicówka niemiecka CDS263D",
    "Wyłącznik nadprądowy 10A niemiecki", "Wyłącznik nadprądowy 16A niemiecki",
    "Wyłącznik nadprądowy 20A niemiecki", "Wyłącznik nadprądowy 25A niemiecki",
    "Gniazdo pojedyńcze niemieckie białe", "Gniazdo podwójne niemieckie czarne",
    "Gniazdo potrójne niemieckie białe", "Gniazdo podwójne hermetyczne niemieckie (IP65)",
    "Gniazdo podłogowe ORNO polskie", "Wyłącznik jednobiegunowy czarny",
    "Łącznik świecznikowy biały", "Wyłącznik schodowy biały",
    "Wyłącznik krzyżowy biały", "Oprawa panel LED BLINGO 120X30 białą",
    "Oprawa panel LED BLINGO 60X60 czarna", "Szynoprzewód czarny 1mb",
    "Szynoprzewód czarny 2mb", "Lampa LED na szynoprzwód czarna",
    "Szynoprzewód biały 1mb", "Szynoprzewód biały 2mb",
    "Lampa LED na szynoprzwód biała", "Lampa łazienkowa",
    "Lampa łazienkowa hermetyczna biała", "Kinkiet Kanlux LED REKA 7W grafit",
    "Kinkiet LED HANA", "Elektroniczny programator czasowy",
    "Czujnik zmierzchu", "czujka ruchu zewnętrzna",
    "czujka ruchu wewnętrzna", "Grzejnik…...............W",
    "Szyna grzebieniowa widełkowa", "Szyna grzebieniowa trójfazowa",
    "Końcówka tulejkowa  TE 1,5-10", "Końcówka tulejkowa  TE 2,5-10",
    "Końcówka tulejkowa  4-12", "Końcówka tulejkowa  10/12",
    "Końcówka tulejkowa  16/12", "Wago zamykane podwójne",
    "Wago zamykane potrójne", "Wago zamykane 5 przewodów",
    "Przewód 3x1,5", "Przewód 3x2,5",
    "Przewód 3x4", "Przewód 5x4",
    "Przewód 5x16", "Przewód 3X16",
    "Przewód 1x10 kolor", "Przewód OLFLEX 4X1,5",
    "Peszel  Ø.....", "Puszka pusta 86x86",
    "Puszka pusta 86x45", "Puszka czarna Hermetyczna  IP65",
    "Dławica PG….....................", "Korytko 32x15",
    "Korytko 40x25", "Korytko 60x40",
    "Korytko 90x60", "Wkręt ocynk 4,2x16",
    "Wkręt czarny OSB", "Skrzynka LAN",
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
