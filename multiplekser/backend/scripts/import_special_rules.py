"""Zapisuje DEFAULT_SPECIAL_RULES (special_rules.py) do Postgresa (Etap 3).

W przeciwienstwie do katalogu (zrodlo: baza_elektryka.json, dane zewnetrzne), zrodlem prawdy dla
regul specjalnych jest kod (DEFAULT_SPECIAL_RULES) - tabela sluzy do tego, zeby Matcher czytal je
jako dane w runtime (mozliwosc edycji bez deployu), a nie zeby byla edytowana rownolegle z kodem.

Idempotentny: klucz naturalny to (rule_type, pattern).

Uzycie:
    python -m scripts.import_special_rules
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.matcher.models import SpecialRuleModel
from app.modules.matcher.special_rules import DEFAULT_SPECIAL_RULES, SpecialRule


def import_special_rules(session: Session, rules: list[SpecialRule]) -> dict[str, int]:
    stats = {"utworzone": 0, "zaktualizowane": 0}
    existing = {(r.rule_type, r.pattern): r for r in session.query(SpecialRuleModel).all()}

    for rule in rules:
        key = (rule.rule_type, rule.pattern)
        row = existing.get(key)
        if row is None:
            row = SpecialRuleModel(rule_type=rule.rule_type, pattern=rule.pattern)
            session.add(row)
            stats["utworzone"] += 1
        else:
            stats["zaktualizowane"] += 1

        row.target_kod = rule.target_kod
        row.kod_template = rule.kod_template
        row.value_regex = rule.value_regex
        row.rounding_steps = rule.rounding_steps
        row.default_value = rule.default_value
        row.normalize = rule.normalize
        row.priority = rule.priority
        row.active = rule.active
        row.description = rule.description

    session.commit()
    return stats


def main() -> None:
    session = SessionLocal()
    try:
        stats = import_special_rules(session, DEFAULT_SPECIAL_RULES)
    finally:
        session.close()

    print(f"Import regul specjalnych zakonczony: {stats['utworzone']} utworzonych, {stats['zaktualizowane']} zaktualizowanych.")


if __name__ == "__main__":
    main()
