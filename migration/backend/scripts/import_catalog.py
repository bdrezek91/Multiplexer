"""Import katalogu z baza_elektryka.json do Postgresa (Etap 2).

Idempotentny: kod produktu jest kluczem - istniejacy produkt jest
aktualizowany (aliasy i warianty magazynowe zastepowane), nowy jest tworzony.

Pola spoza ERD (kod_producenta, zrodlo_stanu, stan) nie sa tracone - trafiaja
do atrybuty['_meta'], bo ERD z Etapu 0 przewiduje dla nich tylko generyczna
kolumne jsonb "atrybuty", a nie sa uzywane przez Parser/Matcher.

Uzycie:
    python -m scripts.import_catalog [sciezka_do_json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel, WarehouseVariantModel

_DEFAULT_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "baza_elektryka.json"

_SECTION_STATUS = {"generyczne": "generyczny", "archiwalne": "archiwalny"}


def _build_atrybuty(rec: dict) -> dict:
    atrybuty = dict(rec.get("atrybuty") or {})
    meta = {
        "kod_producenta": rec.get("kod_producenta"),
        "zrodlo_stanu": rec.get("zrodlo_stanu"),
        "stan": rec.get("stan"),
    }
    if any(v is not None for v in meta.values()):
        atrybuty["_meta"] = meta
    return atrybuty


def import_catalog(session: Session, data: dict) -> dict[str, int]:
    stats = {"utworzone": 0, "zaktualizowane": 0}
    existing = {p.kod: p for p in session.query(ProductModel).all()}

    for section, status in _SECTION_STATUS.items():
        for kod_key, rec in data.get(section, {}).items():
            kod = rec.get("kod", kod_key)
            product = existing.get(kod)
            if product is None:
                product = ProductModel(kod=kod)
                session.add(product)
                stats["utworzone"] += 1
            else:
                stats["zaktualizowane"] += 1
                product.aliasy.clear()
                product.warianty_magazynowe.clear()

            product.nazwa = rec["nazwa"]
            product.jm = rec.get("jm", "SZT")
            product.grupa = rec.get("grupa", "")
            product.status = status
            product.atrybuty = _build_atrybuty(rec)
            product.kolor_domniemany = bool(rec.get("kolor_domniemany", False))

            for alias_text in rec.get("aliasy") or []:
                product.aliasy.append(ProductAliasModel(alias_text=alias_text))

            for magazyn, kod_docelowy in (rec.get("warianty_magazynowe") or {}).items():
                product.warianty_magazynowe.append(
                    WarehouseVariantModel(magazyn=magazyn, kod_docelowy=kod_docelowy)
                )

    session.commit()
    return stats


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_PATH
    data = json.loads(path.read_text(encoding="utf-8"))

    session = SessionLocal()
    try:
        stats = import_catalog(session, data)
    finally:
        session.close()

    print(f"Import zakonczony: {stats['utworzone']} utworzonych, {stats['zaktualizowane']} zaktualizowanych.")


if __name__ == "__main__":
    main()
