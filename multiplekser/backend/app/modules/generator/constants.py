"""Stale pozycje "zawsze dolaczane" - port 1:1 z monolitu (ALWAYS_INCLUDE_BASE, WKRET_OCYNK_ALWAYS,
CABLE_TRAYS_WHITE/BLACK, TRAY_BY_SIZE)."""
from __future__ import annotations

ALWAYS_INCLUDE_BASE: list[dict] = [
    {"kod": "SZYNA GRZEBIENIOWA WIDEŁKOWA", "jm": "SZT"},
    {"kod": "SZYNA GRZEBIENIOWA TRÓJFAZOWA", "jm": "SZT"},
    {"kod": "KOŃCÓWKA TULEJKOWA TE 1,5-10", "jm": "SZT"},
    {"kod": "KOŃCÓWKA TULEJKOWA TE 2,5-10", "jm": "SZT"},
    {"kod": "KOŃCÓWKA TULEJKOWA 4-12", "jm": "SZT"},
    {"kod": "KOŃCÓWKA TULEJKOWA 10/12", "jm": "SZT"},
    {"kod": "WAGO ZAMYKANE PODWÓJNE", "jm": "SZT"},
    {"kod": "WAGO ZAMYKANE POTRÓJNE", "jm": "SZT"},
    {"kod": "WAGO ZAMYKANE 5 PRZEWODÓW", "jm": "SZT"},
    {"kod": "PRZEWÓD 3X1,5", "jm": "M"},
    {"kod": "PRZEWÓD 3X2,5", "jm": "M"},
    {"kod": "PRZEWÓD 3X4 ", "jm": "M"},
    {"kod": "PRZEWÓD 5X4", "jm": "M"},
    {"kod": "PRZEWÓD OLFLEX 4X1,5 (DO KLIMATYZACJI)", "jm": "M"},
]

# WKRĘT OCYNK wydzielony osobno (bug wykryty 2026-07-27, monolit): na fizycznej kartce jest NIZEJ
# niz korytka, wiec dodawany PO nich w generate_output(), nie jako czesc ALWAYS_INCLUDE_BASE.
WKRET_OCYNK_ALWAYS: dict = {"kod": "WKRĘT 4,2X16 (OCYNK) (50 SZT)", "jm": "OPAK"}

CABLE_TRAYS_WHITE: list[dict] = [
    {"kod": "KORYTKO 32X15", "jm": "M"},
    {"kod": "KORYTKO 40X25", "jm": "M"},
    {"kod": "KORYTKO 60X40", "jm": "M"},
]

# R2: stare czarne wiersze formularza zostaly polaczone z nowymi kodami Optimy (2026-09-30):
# 32x15 -> 40x20 (90 STOPNI), 40x25 -> 40x40 (90 STOPNI). Czarna wersja 90x60 nadal nie istnieje.
CABLE_TRAYS_BLACK: list[dict] = [
    {"kod": "KORYTKO CZARNE 40X20 (90 STOPNI)", "jm": "M"},
    {"kod": "KORYTKO CZARNE 40X40 (90 STOPNI)", "jm": "M"},
    {"kod": "KORYTKO CZARNE 60X40", "jm": "M"},
]

# Mapowanie wymiaru Z FORMULARZA -> aktualny kod w Optimie wg koloru projektu. Dla czarnych
# pierwsze dwa wymiary sa nazwami historycznymi na papierze, a nie aktualnymi wymiarami kodu.
# R2: czarne 60x90 celowo brak kodu (None) - nie wolno zgadywac zamiennika.
TRAY_BY_SIZE: dict[str, dict[str, str | None]] = {
    "white": {"15x32": "KORYTKO 32X15", "25x40": "KORYTKO 40X25", "40x60": "KORYTKO 60X40", "60x90": "KORYTKO 90X60"},
    "black": {"15x32": "KORYTKO CZARNE 40X20 (90 STOPNI)", "25x40": "KORYTKO CZARNE 40X40 (90 STOPNI)", "40x60": "KORYTKO CZARNE 60X40", "60x90": None},
}
