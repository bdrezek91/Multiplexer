"""Eksportuje AKTUALNY katalog produktow (oba dzialy) z bazy do jednego pliku JSON - do
porownania z zewnetrznym zrodlem (np. eksportem z Optimy) poza serwerem produkcyjnym, na ktorym
nie ma bezposredniego dostepu do bazy (2026-09-21, na zyczenie uzytkownika: "aktualizacja calego
asortymentu").

Wylacznie do odczytu - nic nie zmienia w bazie. Format wyjsciowy: lista slownikow z kluczowymi
polami potrzebnymi do porownania (kod/nazwa/jm/grupa/status/aliasy/atrybuty), osobno per dzial.

Uzycie (na serwerze produkcyjnym):
    docker compose -f docker-compose.prod.yml exec backend python -m scripts.export_catalog \\
        > katalog_produkcyjny.json
"""
from __future__ import annotations

import json
import sys

from sqlalchemy.orm import Session, selectinload

from app.core.db import SessionLocal
from app.modules.products.models import ProductModel


def export_catalog(session: Session) -> dict[str, list[dict]]:
    rows = (
        session.query(ProductModel)
        .options(selectinload(ProductModel.aliasy), selectinload(ProductModel.warianty_magazynowe))
        .order_by(ProductModel.dzial, ProductModel.kod)
        .all()
    )
    result: dict[str, list[dict]] = {"elektryka": [], "hydraulika": []}
    for row in rows:
        result.setdefault(row.dzial, []).append({
            "kod": row.kod,
            "nazwa": row.nazwa,
            "jm": row.jm,
            "grupa": row.grupa,
            "status": row.status,
            "atrybuty": row.atrybuty or {},
            "aliasy": [a.alias_text for a in row.aliasy],
            "warianty_magazynowe": {w.magazyn: w.kod_docelowy for w in row.warianty_magazynowe},
        })
    return result


def main() -> None:
    session = SessionLocal()
    try:
        data = export_catalog(session)
    finally:
        session.close()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
