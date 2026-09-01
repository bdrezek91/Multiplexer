"""
Reguly specjalne dla konkretnych kodow - jako DANE, nie kod (Etap 3, odlozone w RAPORT_ETAP_1).

Port 1:1 z monolitu (`matchAgainstCatalog()`, komentarze `// R3`/`// R6`, `OCR_TOLERANT_OVERRIDES`):
- "exclude"        - zapytanie dopasowane do wzorca NIGDY nie ma kodu (np. wkret OSB, lampa na
                      szynoprzewod juz wliczona w zestaw, "dziura" 16/12 bez HI).
- "override"       - zapytanie dopasowane do wzorca zwraca wprost `target_kod`, z pominieciem
                      ogolnego dopasowania alias+atrybuty+Dice (reczne wyjatki tolerancyjne na OCR).
- "power_rounding" - wartosc liczbowa z zapytania (regex `value_regex`, domyslnie `default_value`
                      gdy brak) zaokraglana do najblizszej z `rounding_steps` (remis -> pierwszy,
                      mniejszy krok w kolejnosci listy - tak samo jak w JS), wstawiana w `kod_template`.

Jedna regula JS z alternatywa w regexie (`szynoprzewod (czarny|bialy)`) jest tu rozbita na DWA
wiersze (osobno czarny/bialy) - taki sam efekt koncowy (te same wyzwalacze, te same kody wynikowe),
prostszy silnik ewaluacji (bez logiki "ktora grupa przechwycona -> ktory kod").

R1b (stary, wazki tylko dla "Gniazdo podtynkowe z klapka grafit") NIE jest tu przeniesiony -
zweryfikowane testem regresyjnym (test_special_rules.py), ze generalna regula dominujacego kraju
(matcher/core.py, sekcja "R1b UOGOLNIONE") daje identyczny wynik dla tego przypadku.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from app.modules.parser.shared import strip_diacritics

from .result import MatchResult, QUALITY_EXCLUDED


@dataclass
class SpecialRule:
    rule_type: str  # "exclude" | "override" | "power_rounding"
    pattern: str
    target_kod: Optional[str] = None
    kod_template: Optional[str] = None
    value_regex: Optional[str] = None
    rounding_steps: Optional[list[float]] = None
    default_value: Optional[float] = None
    normalize: bool = False
    priority: int = 0
    active: bool = True
    description: str = ""


DEFAULT_SPECIAL_RULES: list[SpecialRule] = [
    SpecialRule(
        rule_type="exclude",
        pattern=r"\blampa\b.*\bszynoprz[e]?w[oó]d\b|\bszynoprz[e]?w[oó]d\b.*\blampa\b",
        priority=10,
        description="Lampa LED na szynoprzewod - juz wliczona w zestaw lamp szynowych.",
    ),
    SpecialRule(
        rule_type="exclude",
        pattern=r"[wn]kr[eę]?t.*osb|osb.*[wn]kr[eę]?t",
        priority=20,
        description="Wkrety OSB nie wchodza do receptury (nie sa towarem elektrycznym).",
    ),
    SpecialRule(
        rule_type="exclude",
        pattern=r"koncow\w*\s*tulejkow\w*.*\b16\s*[/\-]\s*12\b",
        normalize=True,
        priority=30,
        description="Koncowka tulejkowa 16/12 (z lub bez HI) - swiadoma dziura, stan=0.",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"szynoprz[e]?[wv][oó]d\s*czarn\w*",
        target_kod="ZESTAW LAMPY SZYNOWE CZARNE",
        priority=40,
        description="R3: szynoprzewod czarny -> zestaw lamp szynowych czarny.",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"szynoprz[e]?[wv][oó]d\s*bia[łl]\w*",
        target_kod="ZESTAW LAMPY SZYNOWE BIAŁE",
        priority=41,
        description="R3: szynoprzewod bialy -> zestaw lamp szynowych bialy.",
    ),
    SpecialRule(
        rule_type="power_rounding",
        pattern=r"\bgrzejnik\b",
        value_regex=r"(\d+)\s*w\b",
        rounding_steps=[500, 1000, 1500, 2000],
        default_value=2000,
        kod_template="GRZEJNIK {value}W",
        priority=50,
        description="R6: grzejnik - moc_W z tekstu zaokraglona do najblizszej z {500,1000,1500,2000}.",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"[wn]kr[eę]?t.*oc[yv]nk|oc[yv]nk.*[wn]kr[eę]?t",
        target_kod="WKRĘT 4,2X16 (OCYNK) (50 SZT)",
        priority=70,
        description="OCR override: wkret ocynk, tolerancyjny na znieksztalcenia OCR.",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"\bmbn316e\b",
        target_kod="WYŁĄCZNIK NADPRĄDOWY 3P 16A",
        priority=71,
        description="OCR override: MBN316E, dla mocno znieksztalconego OCR (sam kod producenta czytelny).",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"\bpeszel\b",
        target_kod="RURA KARBOWANA FI16",
        priority=72,
        description="OCR override: 'peszel' (nazwa potoczna) -> rura karbowana FI16.",
    ),
    SpecialRule(
        rule_type="override",
        pattern=r"tasma\s*led",
        target_kod="TAŚMA LED DO DEKORÓW",
        normalize=True,
        priority=73,
        description=(
            "Kazda 'tasma led' (dowolny wariant/kolor/dlugosc na kartce) -> TASMA LED DO "
            "DEKOROW, jm=m (na zyczenie uzytkownika, 2026-08-31). Automatyczne doliczenie "
            "'Zasilacz LED 75W' jako osobnej, zapisanej pozycji dokumentu - patrz "
            "documents/tasks.py: _append_auto_zasilacz_led()."
        ),
    ),
]


def _snap_to_step(value: float, steps: list[float]) -> float:
    best, best_diff = steps[0], float("inf")
    for step in steps:
        diff = abs(step - value)
        if diff < best_diff:
            best_diff = diff
            best = step
    return best


def evaluate_special_rules(
    query_name: str,
    rules: list[SpecialRule],
    resolve_by_kod: Callable[[str], MatchResult],
) -> Optional[MatchResult]:
    for rule in sorted((r for r in rules if r.active), key=lambda r: r.priority):
        haystack = strip_diacritics(query_name.lower()) if rule.normalize else query_name
        if not re.search(rule.pattern, haystack, re.IGNORECASE):
            continue

        if rule.rule_type == "exclude":
            return MatchResult(kod=None, nazwa=None, quality=QUALITY_EXCLUDED, ratio=0.0)

        if rule.rule_type == "override":
            return resolve_by_kod(rule.target_kod)

        if rule.rule_type == "power_rounding":
            value_match = re.search(rule.value_regex, query_name, re.IGNORECASE) if rule.value_regex else None
            value = float(value_match.group(1)) if value_match else rule.default_value
            snapped = _snap_to_step(value, rule.rounding_steps)
            kod = rule.kod_template.format(value=int(snapped))
            return resolve_by_kod(kod)

        raise ValueError(f"Nieznany rule_type reguły specjalnej: {rule.rule_type!r}")
    return None


def rules_from_db(session) -> list[SpecialRule]:
    from .models import SpecialRuleModel

    rows = session.query(SpecialRuleModel).all()
    return [
        SpecialRule(
            rule_type=row.rule_type,
            pattern=row.pattern,
            target_kod=row.target_kod,
            kod_template=row.kod_template,
            value_regex=row.value_regex,
            rounding_steps=row.rounding_steps,
            default_value=row.default_value,
            normalize=row.normalize,
            priority=row.priority,
            active=row.active,
            description=row.description,
        )
        for row in rows
    ]
