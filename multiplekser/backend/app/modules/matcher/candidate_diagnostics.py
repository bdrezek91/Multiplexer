"""Diagnostyka zgodnosci kandydat<->zapytanie (Elektryka) - warstwa WYLACZNIE do uzytku
diagnostycznego (Jev shadow, ewentualne przyszle UI/debugowanie).

Celowo NIE jest wywolywana przez match_against_catalog() i nie zmienia go w zaden sposob -
to osobna, czysto-odczytowa funkcja obok istniejacej petli scoringu w core_elektryka.py,
zeby uniknac ryzyka zmiany produkcyjnego wyniku matchera (2026-09-29, Etap 3 integracji
Jev shadow - wymog uzytkownika "zachowaj 100% regresji obecnego matchera"). Odczytuje te
same pola ParsedAttrs/Product i stosuje TA SAMA semantyke porownan co matcher, ale zwraca
strukturalny opis per-atrybut (match/conflict/missing) zamiast samych licznikow.

Jesli w przyszlosci matcher zostanie swiadomie przepisany, zeby korzystac z tej samej
funkcji (unikniecie dwoch rozjezdzajacych sie implementacji) - to osobna, jawna decyzja,
nie dzieje sie automatycznie tutaj."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.modules.parser.core_elektryka import ParsedAttrs
from app.modules.products.catalog import Product

from .core_elektryka import COLOR_TO_JSON, COUNTRY_TO_JSON


@dataclass(frozen=True)
class AttributeSignal:
    match: bool = False
    conflict: bool = False
    missing: bool = False


def _signal(query_value, cand_value) -> AttributeSignal:
    """Brak wartosci w zapytaniu = brak sygnalu (nie wplywa na ranking). Brak wartosci u
    kandydata (przy podanej wartosci w zapytaniu) = "missing" (ostrozny, nie jest to konflikt).
    Rozna wartosc = konflikt, taka sama = dopasowanie."""
    if query_value is None:
        return AttributeSignal()
    if cand_value is None:
        return AttributeSignal(missing=True)
    if query_value == cand_value:
        return AttributeSignal(match=True)
    return AttributeSignal(conflict=True)


@dataclass(frozen=True)
class CandidateDiagnostics:
    country: AttributeSignal
    amp: AttributeSignal
    phase: AttributeSignal
    dim: AttributeSignal
    przekroj: AttributeSignal
    zyl: AttributeSignal
    biegunow: AttributeSignal
    modulow: AttributeSignal
    srednica: AttributeSignal
    color_match: bool
    montaz_conflict: bool

    def as_dict(self) -> dict:
        out: dict = {}
        for name, sig in (
            ("country", self.country), ("amp", self.amp), ("phase", self.phase),
            ("dim", self.dim), ("przekroj", self.przekroj), ("zyl", self.zyl),
            ("biegunow", self.biegunow), ("modulow", self.modulow), ("srednica", self.srednica),
        ):
            out[f"{name}_match"] = sig.match
            out[f"{name}_conflict"] = sig.conflict
            out[f"{name}_missing"] = sig.missing
        out["color_match"] = self.color_match
        out["montaz_conflict"] = self.montaz_conflict
        return out


def diagnose_candidate_elektryka(q: ParsedAttrs, cand: Product) -> CandidateDiagnostics:
    a = cand.atrybuty

    q_country_eff = COUNTRY_TO_JSON.get(q.country) if q.country else None
    country = _signal(q_country_eff, a.get("standard_gniazda"))

    amp = _signal(float(q.amp) if q.amp else None, a.get("prad_A"))

    phase = AttributeSignal()
    if q.phase and cand.phase:
        phase = AttributeSignal(match=(q.phase == cand.phase), conflict=(q.phase != cand.phase))
    elif q.phase and not cand.phase:
        phase = AttributeSignal(missing=True)

    cand_dim: Optional[str] = None
    wymiar = a.get("wymiar_mm")
    if wymiar:
        cand_dim = "x".join(sorted(str(wymiar).split("x")))
    dim = _signal(q.dim, cand_dim)

    przekroj = _signal(q.przekroj, a.get("przekroj_mm2"))
    zyl = _signal(q.zyl, a.get("liczba_zyl"))
    # Konwencja DAMPOL: jesli wydawka nie podaje xP/3P, traktujemy pozycje jako 1P.
    # To jest tylko diagnostyka dla Jev - bazowego matchera i wariantow magazynowych nie zmieniamy.
    q_biegunow_eff = q.biegunow if q.biegunow is not None else 1
    biegunow = _signal(q_biegunow_eff, a.get("liczba_biegunow"))
    modulow = _signal(q.modulow, a.get("liczba_modulow"))
    srednica = _signal(q.srednica, a.get("srednica_mm"))

    q_color_eff = COLOR_TO_JSON.get(q.color, "BIALY") if q.color else None
    cand_color = a.get("kolor") or "BIALY"
    color_match = q_color_eff is None or cand_color == q_color_eff

    cand_montaz = a.get("montaz")
    montaz_conflict = False
    if q.montaz == "NATYNKOWY" and cand_montaz != "NATYNKOWY":
        montaz_conflict = True
    elif q.montaz == "PODTYNKOWY" and cand_montaz and cand_montaz != "PODTYNKOWY":
        montaz_conflict = True
    elif q.montaz == "STALY" and cand_montaz != "STALY":
        montaz_conflict = True

    return CandidateDiagnostics(
        country=country, amp=amp, phase=phase, dim=dim, przekroj=przekroj,
        zyl=zyl, biegunow=biegunow, modulow=modulow, srednica=srednica,
        color_match=color_match, montaz_conflict=montaz_conflict,
    )
