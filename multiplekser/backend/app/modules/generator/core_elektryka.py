"""generate_output() - port 1:1 funkcji generateOutput() z monolitu (sekcja "Generowanie TXT").

Zasady zachowane z monolitu (patrz tam komentarze przy generateOutput):
1) KOLEJNOSC WYNIKU = fizyczna kolejnosc na formularzu (physical_order.physical_order_for), nie
   kolejnosc w jakiej OCR zwrocil pozycje.
2) ALWAYS-INCLUDE ("pierwsza wydawka", parametr first_wydawka) wstawia brakujace pozycje bazy WE
   WLASCIWE MIEJSCE w tej samej fizycznej kolejnosci, nie osobnym blokiem na koncu. Galaz "Excel"
   z monolitu (ORDER_INDEX) jest POZA ZAKRESEM tej migracji - nie ma sciezki importu z Excela.
3) Wkrety OSB: pomijane CALKOWICIE, bez zadnej linii w TXT (odwrotnie niz lampa na szynoprzewod,
   ktora dostaje jawny komentarz "### POMINIETE CELOWO") - to swiadoma asymetria z monolitu.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from typing import Optional

from app.modules.matcher.core_elektryka import match_against_catalog
from app.modules.matcher.result import QUALITY_BAD, QUALITY_EXCLUDED, QUALITY_OK, MatchResult
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES, SpecialRule
from app.modules.products.catalog import Catalog

from .constants import ALWAYS_INCLUDE_BASE, CABLE_TRAYS_BLACK, CABLE_TRAYS_WHITE, TRAY_BY_SIZE, WKRET_OCYNK_ALWAYS
from .detection import detect_dominant_color, detect_dominant_country
from .output_format import format_qty
from .physical_order import physical_order_for

_OSB_RE = re.compile(r"[wn]kr[eę]?t.*osb|osb.*[wn]kr[eę]?t", re.IGNORECASE)
_LAMPA_SZYNO_RE = re.compile(
    r"\blampa\b.*\bszynoprz[e]?w[oó]d\b|\bszynoprz[e]?w[oó]d\b.*\blampa\b", re.IGNORECASE
)
_SZYNO_MB_RE = re.compile(r"szynoprz[e]?[wv][oó]d\s*(czarn\w*|bia[łl]\w*)\s*(\d+)\s*mb?", re.IGNORECASE)
_KORYT_RE = re.compile(r"koryt", re.IGNORECASE)
_KORYT_DIM_RE = re.compile(r"(\d+)\s*[xX]\s*(\d+)")

_ZESTAW_KODY = {"czarny": "ZESTAW LAMPY SZYNOWE CZARNE", "biały": "ZESTAW LAMPY SZYNOWE BIAŁE"}
_VERY_LOW_RATIO = 0.2


@dataclass
class GeneratorItem:
    name: str
    qty: float
    off_form: bool = False
    # Dopasowanie juz zapisane na pozycji dokumentu (z pierwszego OCR albo z recznej korekty
    # przez PATCH .../items/{item_id}) - patrz uzycie ponizej, "reczna korekta trafia do TXT".
    match_kod: Optional[str] = None
    match_nazwa: Optional[str] = None
    match_jm: Optional[str] = None
    match_quality: Optional[str] = None


@dataclass
class GenerateResult:
    lines: list[str]
    dominant_color: str
    dominant_country: str
    color_counts: dict[str, int]
    warning_no_magazyn: bool


def _tray_kod_for(name: str, current_color: str) -> Optional[str] | dict:
    """Zwraca kod (str) gdy jest dopasowanie, {'blocked': True} gdy to swiadomie nieistniejacy
    wariant (nie wolno zgadywac zamiennika), albo None gdy to w ogole nie korytko."""
    if not _KORYT_RE.search(name):
        return None
    dm = _KORYT_DIM_RE.search(name)
    if not dm:
        return None
    a, b = sorted((int(dm.group(1)), int(dm.group(2))))
    key = f"{a}x{b}"
    color_key = "black" if current_color == "black" else "white"
    kod = TRAY_BY_SIZE[color_key].get(key)
    if kod:
        return kod
    if current_color == "black" and key == "60x90":
        return {"blocked": True}
    return None


def generate_output(
    items: list[GeneratorItem],
    catalog: Catalog,
    magazyn: Optional[str],
    special_rules: Optional[list[SpecialRule]] = None,
    qty_mode: str = "real",
    first_wydawka: bool = False,
) -> GenerateResult:
    rules = DEFAULT_SPECIAL_RULES if special_rules is None else special_rules

    # 1) Sortowanie wg fizycznej kolejnosci kartki - pozycje bez rozsadnego dopasowania zostaja
    #    w swojej wzglednej kolejnosci na koncu (unikalny fallback 10000+i per pozycja).
    ordered = sorted(
        enumerate(items), key=lambda pair: physical_order_for(pair[1].name, 10000 + pair[0])
    )
    sorted_items = [it for _, it in ordered]

    item_names = [it.name for it in sorted_items]
    current_color, color_counts = detect_dominant_color(item_names)
    dominant_country = detect_dominant_country(item_names, catalog)

    seq: list[dict] = []
    kod_index: dict[str, int] = {}
    szyno_index = {"czarny": -1, "biały": -1}
    szyno = {"czarny": 0.0, "biały": 0.0}

    def add_kod(kod: str, qty: float, jm: str) -> None:
        if kod in kod_index:
            seq[kod_index[kod]]["qty"] += qty
            return
        kod_index[kod] = len(seq)
        seq.append({"type": "kod", "kod": kod, "qty": qty, "jm": jm})

    for it in sorted_items:
        name = it.name.lower()

        if _OSB_RE.search(name):
            continue

        if _LAMPA_SZYNO_RE.search(name):
            seq.append({
                "type": "excluded",
                "text": f"### POMINIETE CELOWO (lampa na szynoprzewód - juz w zestawie): "
                        f"{it.name};{format_qty(it.qty)};;SZT;{magazyn or ''}",
            })
            continue

        m2 = _SZYNO_MB_RE.search(name)
        if m2:
            color = "czarny" if m2.group(1).startswith("czarn") else "biały"
            szyno[color] += it.qty * int(m2.group(2))
            if szyno_index[color] < 0:
                szyno_index[color] = len(seq)
                kod_index[_ZESTAW_KODY[color]] = szyno_index[color]
                seq.append({"type": "kod", "kod": _ZESTAW_KODY[color], "qty": 0.0, "jm": "SZT"})
            continue

        tray = _tray_kod_for(it.name, current_color)
        if isinstance(tray, dict) and tray.get("blocked"):
            seq.append({
                "type": "unmatched",
                "text0": f"### BRAK DOPASOWANIA (korytko czarne 90x60 nie istnieje w Optimie - "
                         f"sprawdz recznie): {it.name}",
                "qty": it.qty, "jm": "M",
            })
            continue
        if isinstance(tray, str):
            add_kod(tray, it.qty, "M")
            continue

        # Reczna korekta (PATCH .../items/{item_id}) albo juz-dobre dopasowanie z pierwszego OCR
        # ma pierwszenstwo przed ponownym dopasowywaniem od zera - inaczej generator ignorowal
        # poprawki uzytkownika i eksportowal "BRAK DOPASOWANIA" mimo poprawionego kodu w UI.
        if it.match_quality == QUALITY_OK and it.match_kod:
            match = MatchResult(
                kod=it.match_kod, nazwa=it.match_nazwa, quality=QUALITY_OK, ratio=1.0,
                jm_override=it.match_jm,
            )
        else:
            match = match_against_catalog(it.name, catalog, dominant_country=dominant_country, magazyn=magazyn, special_rules=rules)
        if it.off_form and match.quality == QUALITY_OK and match.ratio < 0.70:
            match = replace(match, quality=QUALITY_BAD)

        if match.quality == QUALITY_EXCLUDED:
            seq.append({
                "type": "excluded",
                "text": f"### POMINIETE CELOWO: {it.name};{format_qty(it.qty)};;SZT;{magazyn or ''}",
            })
            continue

        jm = match.jm_override or "SZT"
        if match.quality == QUALITY_OK and match.kod:
            add_kod(match.kod, it.qty, jm)
            continue

        if it.off_form and match.quality == QUALITY_BAD:
            seq.append({
                "type": "excluded",
                "text": f'Elektryka;1;DOPISEK SPOZA FORMULARZA - oryginal: "{it.name}", '
                        f"ilosc na kartce: {format_qty(it.qty)};szt;{magazyn or ''}",
            })
            continue

        if match.kod and match.ratio >= _VERY_LOW_RATIO:
            podpowiedz = f"podpowiedz: {match.kod}"
        else:
            podpowiedz = "brak sensownej podpowiedzi (zbyt niskie podobienstwo - sprawdz recznie)"
        seq.append({
            "type": "unmatched",
            "text0": f"### BRAK DOPASOWANIA (sprawdz recznie - {podpowiedz}): {it.name}",
            "qty": it.qty, "jm": jm,
        })

    # R3: zestawy szynoprzewod - metry lacznie / dzielnik (z pola przelicznik w JSON) = szt zestawu.
    for color in ("czarny", "biały"):
        if szyno_index[color] >= 0:
            kod = _ZESTAW_KODY[color]
            rec = catalog.find_by_kod(kod)
            dzielnik = 2
            if rec is not None:
                przelicznik = (rec.atrybuty.get("_meta") or {}).get("przelicznik")
                if przelicznik and przelicznik.get("dzielnik"):
                    dzielnik = przelicznik["dzielnik"]
            q = szyno[color] / dzielnik
            entry = seq[szyno_index[color]]
            if q > 0:
                entry["qty"] = q
            else:
                entry["type"] = "drop"

    # R4: wkret ocynk - przelicznik ZAWSZE Math.ceil(szt/opak), rowniez ponizej opak (np. 30 -> 1).
    kod_wkret = WKRET_OCYNK_ALWAYS["kod"]
    if kod_wkret in kod_index:
        entry = seq[kod_index[kod_wkret]]
        rec = catalog.find_by_kod(kod_wkret)
        opak = 50
        if rec is not None:
            meta_opak = (rec.atrybuty.get("_meta") or {}).get("przelicznik_opak")
            if meta_opak:
                opak = meta_opak
        entry["qty"] = float(math.ceil(entry["qty"] / opak))

    # Tryb "Wszystko po 1 szt"
    if qty_mode == "ones":
        for entry in seq:
            if entry["type"] in ("kod", "unmatched"):
                entry["qty"] = 1.0

    out_lines: list[str] = []
    out_kody: list[Optional[str]] = []
    for entry in seq:
        if entry["type"] == "drop":
            continue
        if entry["type"] == "kod":
            out_lines.append(f"{entry['kod']};{format_qty(entry['qty'])};;{entry['jm']};{magazyn or ''}")
            out_kody.append(entry["kod"])
        elif entry["type"] == "unmatched":
            out_lines.append(f"{entry['text0']};{format_qty(entry['qty'])};;{entry['jm']};{magazyn or ''}")
            out_kody.append(None)
        else:
            out_lines.append(entry["text"])
            out_kody.append(None)

    # Always-include ("pierwsza wydawka"): brakujace pozycje bazy wstawiane WE WLASCIWE MIEJSCE
    # wzgledem fizycznej kolejnosci formularza (galaz Excel/ORDER_INDEX z monolitu poza zakresem).
    if first_wydawka:
        included_kody = {k for k in out_kody if k}
        always_include = list(ALWAYS_INCLUDE_BASE)
        always_include += CABLE_TRAYS_BLACK if current_color == "black" else CABLE_TRAYS_WHITE
        always_include.append(WKRET_OCYNK_ALWAYS)
        missing = [ai for ai in always_include if ai["kod"] not in included_kody]
        for ai in missing:
            target = physical_order_for(ai["kod"])
            insert_at = len(out_lines)
            for i, kod in enumerate(out_kody):
                if not kod:
                    continue
                if physical_order_for(kod) > target:
                    insert_at = i
                    break
            out_lines.insert(insert_at, f"{ai['kod']};1;;{ai['jm']};{magazyn or ''}")
            out_kody.insert(insert_at, ai["kod"])
            included_kody.add(ai["kod"])

    return GenerateResult(
        lines=out_lines,
        dominant_color=current_color,
        dominant_country=dominant_country,
        color_counts=color_counts,
        warning_no_magazyn=not magazyn and bool(out_lines),
    )
