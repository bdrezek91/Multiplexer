"""generate_output_hydraulika() - port 1:1 funkcji generateOutput() z Multipekser_Hydraulika.html.

OSOBNA funkcja od generate_output() (Elektryka) - ten sam wzorzec co parser/matcher (patrz
CLAUDE.md, "Decyzja architektoniczna"). Zasady zachowane ze zrodla (komentarz nad
generateOutput() w monolicie, zweryfikowany bezposrednio, nie zgadywany):

1) KOLEJNOSC WYNIKU = kolejnosc pozycji w dokumencie zrodlowym (PDF/skan), NIE fizyczna
   kolejnosc formularza jak w Elektryce (`physical_order_for`) - Hydraulika nigdy nie miala tej
   funkcji. Duplikaty (ten sam kod Optimy) scalane w miejscu PIERWSZEGO wystapienia.
2) Brak jakiegokolwiek "always-include"/"pierwsza wydawka" - hydraulika nie ma pozycji
   dopisywanych domyslnie do kazdej receptury (funkcja nie przyjmuje wiec parametru
   `first_wydawka` w ogole, nie tylko go ignoruje).
3) Brak dominujacego koloru/kraju, brak konsolidacji specyficznej dla Elektryki (koryta
   kablowe, szynoprzewody, wkrety OSB) - te pojecia nie istnieja w zrodle Hydrauliki.
4) Tylko `quality == QUALITY_OK` trafia do wyniku jako dopasowany kod. WARN i BAD (tak samo)
   staja sie linia "### BRAK DOPASOWANIA" - identyczne traktowanie WARN/BAD jak juz ma
   Elektryka (`generator/core.py`), ale bez niuansu `_VERY_LOW_RATIO` (Hydraulika w zrodle
   zawsze podaje "podpowiedz: {kod}" gdy jest jakikolwiek kod, inaczej "brak" - bez progu
   podobienstwa rozstrzygajacego, czy podpowiedz ma sens).
5) ZESTAW MEBLI BIAŁYCH (2026-08-07, na zyczenie uzytkownika): "Szafka stojaca 40/80 cm biala",
   "Szafka wiszaca 40/80 cm biala", "Szafka okapowa 60 cm biala" NIE MAJA WLASNYCH kodow w
   katalogu Optima (nie istnieja jako osobne produkty - sprzedawane sa WYLACZNIE w komplecie
   jako "ZESTAW MEBLI BIAŁYCH"), dlatego bez tej reguly zawsze ladowaly do "### BRAK
   DOPASOWANIA". Jesli na dokumencie wystapia co najmniej 3 z tych 5 pozycji (dowolne, w
   dowolnych ilosciach - pracownik czasem nie dopisuje np. okapowej, mimo ze fizycznie wchodzi
   w sklad zestawu) - wszystkie obecne z tych 5 znikaja z wyniku, zastapione JEDNYM wierszem
   "ZESTAW MEBLI BIAŁYCH" z ILOSCIA ZAWSZE RÓWNĄ 1 (zestaw to zawsze jeden komplet mebli do
   jednej lazienki/kuchni, ilosc poszczegolnych elementow na wydawce nie ma tu znaczenia).
   Ponizej 3 z 5 - bez zmian, pozycje zostaja nierozpoznane (jak dotad).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.modules.matcher import match_against_catalog_hydraulika
from app.modules.matcher.result import QUALITY_OK, MatchResult
from app.modules.parser.shared import strip_diacritics
from app.modules.products.catalog import Catalog

from .core_elektryka import GeneratorItem
from .output_format import format_qty

_ZESTAW_MEBLI_BIALYCH_KOD = "ZESTAW MEBLI BIAŁYCH"
_ZESTAW_MEBLI_BIALYCH_MIN_ELEMENTOW = 3


def _norm_nazwa(value: str) -> str:
    return strip_diacritics((value or "").strip().lower())


_ZESTAW_MEBLI_BIALYCH_ELEMENTY = {
    _norm_nazwa(nazwa) for nazwa in (
        "Szafka stojąca 40 cm biała",
        "Szafka stojąca 80 cm biała",
        "Szafka wisząca 40 cm biała",
        "Szafka wisząca 80 cm biała",
        "Szafka okapowa 60 cm biała",
    )
}


def _merge_zestaw_mebli_bialych(items: list[GeneratorItem]) -> list[GeneratorItem]:
    matched_idx = [
        i for i, it in enumerate(items) if _norm_nazwa(it.name) in _ZESTAW_MEBLI_BIALYCH_ELEMENTY
    ]
    if len(matched_idx) < _ZESTAW_MEBLI_BIALYCH_MIN_ELEMENTOW:
        return items

    zestaw = GeneratorItem(
        name=_ZESTAW_MEBLI_BIALYCH_KOD, qty=1.0,
        match_kod=_ZESTAW_MEBLI_BIALYCH_KOD, match_nazwa="Zestaw mebli białych",
        match_jm="SZT", match_quality=QUALITY_OK, match_score=1.0,
    )
    matched_set = set(matched_idx)
    out = [it for i, it in enumerate(items) if i not in matched_set]
    # Wstawiamy zestaw na miejscu PIERWSZEGO polaczonego elementu, zeby zachowac zasade 1)
    # (kolejnosc wyniku = kolejnosc w dokumencie zrodlowym) tak blisko oryginalu, jak sie da.
    # Nic wczesniejszego nie zostalo usuniete (to najmniejszy usuniety indeks), wiec pozycja
    # w `out` pokrywa sie wprost z oryginalnym indeksem.
    out.insert(min(matched_idx), zestaw)
    return out


@dataclass
class GenerateResultHydraulika:
    lines: list[str]
    warning_no_magazyn: bool


def generate_output_hydraulika(
    items: list[GeneratorItem],
    catalog: Catalog,
    magazyn: Optional[str],
    qty_mode: str = "real",
) -> GenerateResultHydraulika:
    items = _merge_zestaw_mebli_bialych(items)
    seq: list[dict] = []
    kod_index: dict[str, int] = {}

    def add_kod(kod: str, qty: float, jm: str) -> None:
        if kod in kod_index:
            seq[kod_index[kod]]["qty"] += qty
            return
        kod_index[kod] = len(seq)
        seq.append({"type": "kod", "kod": kod, "qty": qty, "jm": jm})

    for it in items:
        # Reczna korekta (PATCH .../items/{item_id}) albo juz-dobre dopasowanie z pierwszego OCR
        # ma pierwszenstwo przed ponownym dopasowywaniem od zera - inaczej generator ignorowal
        # poprawki uzytkownika i eksportowal "BRAK DOPASOWANIA" mimo poprawionego kodu w UI.
        if it.match_quality == QUALITY_OK and it.match_kod:
            match = MatchResult(
                kod=it.match_kod, nazwa=it.match_nazwa, quality=QUALITY_OK,
                ratio=it.match_score if it.match_score is not None else 1.0,
                jm_override=it.match_jm,
            )
        else:
            match = match_against_catalog_hydraulika(it.name, catalog, magazyn=magazyn)
        jm = match.jm_override or "SZT"

        if match.quality == QUALITY_OK and match.kod:
            add_kod(match.kod, it.qty, jm)
            continue

        podpowiedz = f"podpowiedz: {match.kod}" if match.kod else "brak"
        seq.append({
            "type": "unmatched",
            "text0": f"### BRAK DOPASOWANIA (sprawdz recznie - {podpowiedz}): {it.name}",
            "qty": it.qty, "jm": jm,
        })

    if qty_mode == "ones":
        for entry in seq:
            entry["qty"] = 1.0

    out_lines: list[str] = []
    for entry in seq:
        if entry["type"] == "kod":
            out_lines.append(f"{entry['kod']};{format_qty(entry['qty'])};;{entry['jm']};{magazyn or ''}")
        else:
            out_lines.append(f"{entry['text0']};{format_qty(entry['qty'])};;{entry['jm']};{magazyn or ''}")

    return GenerateResultHydraulika(
        lines=out_lines,
        warning_no_magazyn=not magazyn and bool(out_lines),
    )
