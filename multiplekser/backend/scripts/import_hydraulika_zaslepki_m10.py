"""Dodaje dwa zweryfikowane kody zaslepek M10 do katalogu Hydrauliki.

Idempotentne i celowo punktowe - nie reimportuje calego starego fixture katalogu.
"""
from app.core.db import SessionLocal
from app.modules.products.models import ProductModel

PRODUCTS = [
    {
        "kod": "ZAŚLEPKA M10 CZARNA + PODKŁADKA",
        "nazwa": "Zaślepka M10 czarna + podkładka",
        "kolor": "CZARNY",
    },
    {
        "kod": "ZAŚLEPKA M10 BIAŁA + PODKŁADKA",
        "nazwa": "Zaślepka M10 biała + podkładka",
        "kolor": "BIALY",
    },
]


def main() -> None:
    session = SessionLocal()
    try:
        for rec in PRODUCTS:
            row = session.query(ProductModel).filter_by(kod=rec["kod"], dzial="hydraulika").first()
            if row is None:
                row = ProductModel(kod=rec["kod"], dzial="hydraulika")
                session.add(row)
            row.nazwa = rec["nazwa"]
            row.jm = "SZT"
            row.grupa = "Mocowania i drobny osprzęt"
            row.status = "generyczny"
            row.atrybuty = {
                "srednica_mm": None,
                "kat_st": None,
                "gwint_cal": None,
                "material": None,
                "zlacze": None,
                "dlugosc_cm": None,
                "pojemnosc_l": None,
                "moc_W": None,
                "wymiar_mm": None,
                "kolor": rec["kolor"],
                "dn": None,
                "pn": None,
                "gwint_metryczny": "M10",
            }
            row.kolor_domniemany = False
        session.commit()
        print("OK: zaslepki M10 czarna/biala sa w katalogu Hydrauliki")
    finally:
        session.close()


if __name__ == "__main__":
    main()
