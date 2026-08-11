"""Detekcja koloru/kraju dominujacego projektu - port detectDominantColor()/detectDominantCountry()
z monolitu (sekcja "DETEKCJA KOLORU DOMINUJACEGO PROJEKTU", port z Multiplekser Excel).
"""
from __future__ import annotations

from app.modules.matcher.core_elektryka import match_against_catalog
from app.modules.products.catalog import Catalog

_BLACK_KEYWORDS = ("czarny", "czarna", "czarne", "czarnych")
_WHITE_KEYWORDS = ("biały", "biała", "białe", "białych")
_COLOR_RELEVANT = ("rozdzielnic", "gniazd", "wyłącznik", "łącznik", "opraw", "puszk", "kinkiet", "lamp")


def detect_dominant_color(item_names: list[str]) -> tuple[str, dict[str, int]]:
    """Jesli w rozpoznanych pozycjach wystepuje przewaga liczebna czarnych elementow osprzetu nad
    bialymi -> projekt "black"; w przeciwnym razie (rowniez remis) "white". Liczone tylko wsrod
    nazw zawierajacych slowo-klucz z grupy "kolorowo istotnej" (gniazda, wylaczniki, oprawy...).
    Zwraca (kolor, {"black": n, "white": n}) - liczniki uzywane tez do wyswietlenia uzytkownikowi
    (patrz updateColorBadge() w monolicie)."""
    black_count = 0
    white_count = 0
    for name in item_names:
        low = (name or "").lower()
        if not any(kw in low for kw in _COLOR_RELEVANT):
            continue
        if any(kw in low for kw in _BLACK_KEYWORDS):
            black_count += 1
        if any(kw in low for kw in _WHITE_KEYWORDS):
            white_count += 1
    color = "black" if black_count > white_count else "white"
    return color, {"black": black_count, "white": white_count}


def detect_dominant_country(item_names: list[str], catalog: Catalog) -> str:
    """R1b: dominujacy standard PL/DE calego projektu. Dopasowanie wykonywane BEZ znanego jeszcze
    kraju/magazynu (unika cyklu: kraj jest dopiero wyliczany), tylko dla grup Gniazda/Łączniki.
    Remis -> PL."""
    pl_count = 0
    de_count = 0
    for name in item_names:
        match = match_against_catalog(name, catalog, dominant_country=None, magazyn=None)
        if not match.kod:
            continue
        cand = catalog.find_by_kod(match.kod)
        if not cand or cand.grupa not in ("Gniazda", "Łączniki"):
            continue
        std = cand.atrybuty.get("standard_gniazda")
        if std == "PL":
            pl_count += 1
        elif std == "DE":
            de_count += 1
    return "DE" if de_count > pl_count else "PL"
