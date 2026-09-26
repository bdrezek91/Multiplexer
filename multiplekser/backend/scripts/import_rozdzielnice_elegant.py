"""Dodaje do katalogu (Elektryka) rozdzielnice "Elegant" - 2026-09-26, na zyczenie uzytkownika:
2 nowe pozycje z eksportu Optimy ("ROZDZIELNICA ELEGANT 24" i jej multimedialny wariant), z
prosba o "inteligentne" rozroznianie wariantow po slowach-kwalifikatorach (elegant/multimedialna).

Mechanizm: alias_hits() (matcher/shared.py) zwraca TYLKO kandydatow, ktorych NAJBARDZIEJ
SPECYFICZNY (najdluzszy) pasujacy alias ma najwiecej tokenow ze wszystkich znalezionych - wiec
wystarczy dac wariantowi z dodatkowym slowem (multimedialna) alias z tym slowem WIECEJ tokenow
niz alias bazowego wariantu:
- "ROZDZIELNICA ELEGANT 24" (bez multimedialnej) -> alias 2-tokenowy "elegant 24" - trafia,
  gdy w tekscie NIE MA slowa "multimedialna" (bo wtedy oba warianty by pasowaly, a ten
  multimedialny wygrywa specyficznoscia).
- "ROZDZIELNICA ELEGANT MULTIMEDIALNA 24" -> alias 3-tokenowy "elegant multimedialna 24" (plus
  2-tokenowy zapasowy "multimedialna 24" na wypadek gdyby OCR zgubil slowo "elegant") - zawsze
  wygrywa nad wariantem bazowym, gdy "multimedialna" jest w tekscie.

Ten sam wzorzec nalezy powielac dla kolejnych rodzin "produkt bazowy + wariant z dodatkowym
kwalifikatorem" (np. przyszle "... PREMIUM"/"... XL" itp.) - patrz tez
scripts/import_kopos_pokrywy_koryt.py dla analogicznego, wczesniejszego podejscia.

Idempotentny: klucz naturalny to (kod, dzial="elektryka"). Istniejacy produkt NIE jest
nadpisywany (nazwa/jm/grupa) - dopisywane sa tylko brakujace aliasy.

Uzycie:
    python -m scripts.import_rozdzielnice_elegant
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

GRUPA = "Rozdzielnice i osprzęt"
DZIAL = "elektryka"

# (kod, nazwa, jm, aliasy)
PRODUCTS: list[tuple[str, str, str, list[str]]] = [
    (
        "ROZDZIELNICA ELEGANT 24", "Rozdzielnica Elegant 24", "SZT",
        ["rozdzielnica elegant 24", "elegant 24"],
    ),
    (
        "ROZDZIELNICA ELEGANT MULTIMEDIALNA 24", "Rozdzielnica Elegant multimedialna 24", "SZT",
        ["rozdzielnica elegant multimedialna 24", "elegant multimedialna 24", "multimedialna 24"],
    ),
]


def import_rozdzielnice_elegant(session: Session) -> dict[str, int]:
    stats = {"utworzone": 0, "aliasy_dopisane": 0, "bez_zmian": 0}
    existing = {
        row.kod: row
        for row in session.query(ProductModel).filter(ProductModel.dzial == DZIAL).all()
    }

    for kod, nazwa, jm, aliasy in PRODUCTS:
        row = existing.get(kod)
        if row is None:
            row = ProductModel(kod=kod, nazwa=nazwa, jm=jm, grupa=GRUPA, dzial=DZIAL, status="generyczny")
            row.aliasy = [ProductAliasModel(alias_text=a) for a in aliasy]
            session.add(row)
            stats["utworzone"] += 1
            continue

        present = {a.alias_text for a in row.aliasy}
        missing = [a for a in aliasy if a not in present]
        if missing:
            row.aliasy.extend(ProductAliasModel(alias_text=a) for a in missing)
            stats["aliasy_dopisane"] += len(missing)
        else:
            stats["bez_zmian"] += 1

    session.commit()
    return stats


def main() -> None:
    session = SessionLocal()
    try:
        stats = import_rozdzielnice_elegant(session)
    finally:
        session.close()

    print(
        f"Import rozdzielnic Elegant zakonczony: {stats['utworzone']} utworzonych produktow, "
        f"{stats['aliasy_dopisane']} dopisanych aliasow, {stats['bez_zmian']} bez zmian."
    )


if __name__ == "__main__":
    main()
