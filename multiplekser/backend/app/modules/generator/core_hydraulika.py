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
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.modules.matcher import match_against_catalog_hydraulika
from app.modules.matcher.result import QUALITY_OK
from app.modules.products.catalog import Catalog

from .core_elektryka import GeneratorItem
from .output_format import format_qty


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
    seq: list[dict] = []
    kod_index: dict[str, int] = {}

    def add_kod(kod: str, qty: float, jm: str) -> None:
        if kod in kod_index:
            seq[kod_index[kod]]["qty"] += qty
            return
        kod_index[kod] = len(seq)
        seq.append({"type": "kod", "kod": kod, "qty": qty, "jm": jm})

    for it in items:
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
