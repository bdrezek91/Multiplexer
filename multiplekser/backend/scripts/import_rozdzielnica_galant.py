"""Dodaje do katalogu (Elektryka) "ROZDZIELNICA HERMETYCZNA 1X18 (GALANT)" - 2026-10-05, na
zyczenie uzytkownika: zgloszenie pracownika (marzena.wiesner-szmit@dampol-investment.com),
dokument 20261001135350826.pdf - OCR rozpoznal "rozdzielnica GALANT PLUS RN-1x18 IP 65", ale
w katalogu nie bylo ZADNEGO produktu o tej nazwie handlowej (producenta) - matcher poprawnie
nie zgadl (match_kod=None, quality=bad), a Jev w trybie active rowniez zwrocil OTHER i
wyczyscil dopasowanie zamiast zgadywac (patrz decision/active.py: "Jev OTHER + slaby matcher
= nie eksportujemy przypadkowego kodu") - oba mechanizmy zadzialaly poprawnie, brakowalo tylko
samego produktu w bazie.

Idempotentny: klucz naturalny to (kod, dzial="elektryka"). Istniejacy produkt NIE jest
nadpisywany (nazwa/jm/grupa/atrybuty) - dopisywane sa tylko brakujace aliasy.

Uzycie:
    python -m scripts.import_rozdzielnica_galant
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

GRUPA = "Rozdzielnice i osprzęt"
DZIAL = "elektryka"

KOD = "ROZDZIELNICA HERMETYCZNA 1X18 (GALANT)"
NAZWA = "Rozdzielnica hermetyczna 1x18 (Galant)"
JM = "SZT"
ATRYBUTY = {
    "hermetyczny": True,
    "stopien_ip": "IP65",
    "liczba_modulow": 18,
    "kolor": "BIALY",
}
ALIASY = [
    "rozdzielnica galant plus rn-1x18",
    "galant plus rn-1x18",
    "galant plus",
    "rozdzielnica galant",
    "galant",
]


def import_rozdzielnica_galant(session: Session) -> str:
    row = (
        session.query(ProductModel)
        .filter(ProductModel.dzial == DZIAL, ProductModel.kod == KOD)
        .first()
    )

    if row is None:
        row = ProductModel(
            kod=KOD, nazwa=NAZWA, jm=JM, grupa=GRUPA, dzial=DZIAL,
            status="generyczny", atrybuty=dict(ATRYBUTY),
        )
        row.aliasy = [ProductAliasModel(alias_text=a) for a in ALIASY]
        session.add(row)
        session.commit()
        return f"Utworzono produkt {KOD!r} z {len(ALIASY)} aliasami."

    present = {a.alias_text for a in row.aliasy}
    missing = [a for a in ALIASY if a not in present]
    if missing:
        row.aliasy.extend(ProductAliasModel(alias_text=a) for a in missing)
        session.commit()
        return f"Produkt {KOD!r} juz istnial - dopisano aliasy: {missing}."

    session.commit()
    return f"Produkt {KOD!r} juz istnial z kompletem aliasow - bez zmian."


def main() -> None:
    session = SessionLocal()
    try:
        wynik = import_rozdzielnica_galant(session)
    finally:
        session.close()
    print(wynik)


if __name__ == "__main__":
    main()
