"""Automatyczne wykrywanie grup niemal identycznych wierszy formularza (2026-09-17).

Kontekst: prompt OCR probowal dotad zapobiegac pomyleniu "podobnych wierszy" (np. "Rozdzielnica
SRN 12/24/36/48") wylacznie WYMIENIAJAC je z nazwy jako przyklady w tekscie instrukcji
(_PODOBNE_WIERSZE_DOPISEK w prompt.py). Zwalidowane na realnym przypadku produkcyjnym
(2026-09-17): grupy JUZ wymienione w przykladach zostaly odczytane bezblednie, ale strukturalnie
identyczna grupa "Przewod 3x1,5/3x2,5/3x4/..." (nie wymieniona) zostala pomylona o dwa wiersze -
sam tekst instrukcji nie skaluje sie (nie da sie wymienic z nazwy kazdej mozliwej grupy, a model
mimo ogolnego zdania "grupy roznaice sie tylko liczba" nie stosuje tej ostroznosci jednakowo do
grup spoza listy przykladow).

Ten modul NIE poprawia tekstu promptu - wylicza grupy AUTOMATYCZNIE z kanonicznej listy wierszy
formularza (FORM_ROWS), zeby uzyc ich jako cel DODATKOWEJ, niezaleznej kontroli AI (patrz
ocr/verify.py: verify_row_group_alignment) zamiast tylko podpowiedzi w tekscie. Samosynchronizuje
sie z FORM_ROWS bez recznej konserwacji listy grup.

Metoda: dwie etykiety naleza do tej samej grupy, jesli po zastapieniu KAZDEGO ciagu
cyfr/przecinkow/kropek/myslnikow/"x" jednym symbolem "#" staja sie identyczne, np.:
  "Rozdzielnica SRN 12 biała"      -> "Rozdzielnica SRN # biała"
  "Rozdzielnica SRN 24 biała"      -> "Rozdzielnica SRN # biała"   (ta sama grupa)
  "Przewód 3x1,5"                  -> "Przewód #"
  "Przewód 3x4"                    -> "Przewód #"                  (ta sama grupa)
  "Puszka czarna Hermetyczna IP65" -> "Puszka czarna Hermetyczna IP#" (osobna grupa/singleton)
"""
from __future__ import annotations

import re
from collections import defaultdict

_VARIANT_RUN = re.compile(r"[0-9][0-9,.\-xX]*")


def _stem(label: str) -> str:
    return _VARIANT_RUN.sub("#", label)


def group_similar_rows(canonical_labels: list[str]) -> list[list[str]]:
    """Zwraca grupy (>=2 elementy) etykiet rozniacych sie tylko liczba/wymiarem/przekrojem.
    Kolejnosc grup i czlonkow w grupie - taka jak w `canonical_labels` (stabilna, deterministyczna)."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for label in canonical_labels:
        buckets[_stem(label)].append(label)
    return [members for members in buckets.values() if len(members) >= 2]
