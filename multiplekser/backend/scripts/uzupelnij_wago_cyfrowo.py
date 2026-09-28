"""Dodaje do istniejacych produktow WAGO ZAMYKANE PODWÓJNE/POTRÓJNE aliasy w formie cyfrowej
("2/3 przewody/przewodów") - 2026-09-29, na zyczenie uzytkownika ("Wago zamykane 3 przewodów"
nie trafialo pewnie w POTRÓJNE, bo katalog mial tylko slowna forme "potrójne", a "4"/"5"
przewodowe warianty juz sa nazwane cyfrowo w katalogu (WAGO ZAMYKANE 4 PRZEWODY/5 PRZEWODÓW) -
niespojnosc pomiedzy 2/3 (slownie) a 4/5 (cyfrowo) powodowala falszywe "spoza formularza" dla
najczestszego, w pelni poprawnego zapisu cyfrowego 2/3-przewodowego waga.

Idempotentny: dopisuje tylko brakujace aliasy, nic nie nadpisuje.

Uzycie:
    docker compose -f docker-compose.prod.yml exec backend python -m scripts.uzupelnij_wago_cyfrowo
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

# (fragment kodu, nowe aliasy)
POPRAWKI: list[tuple[str, list[str]]] = [
    ("WAGO ZAMYKANE PODWÓJNE", ["2 przewody", "2 przewodów"]),
    ("WAGO ZAMYKANE POTRÓJNE", ["3 przewody", "3 przewodów"]),
]


def uzupelnij(session: Session) -> str:
    wyniki = []
    for fragment_kodu, nowe_aliasy in POPRAWKI:
        row = (
            session.query(ProductModel)
            .options(selectinload(ProductModel.aliasy))
            .filter(ProductModel.dzial == "elektryka", ProductModel.kod == fragment_kodu)
            .first()
        )
        if row is None:
            wyniki.append(f"Nie znaleziono produktu {fragment_kodu!r} - pominieto.")
            continue

        istniejace = {a.alias_text for a in row.aliasy}
        dopisane = [a for a in nowe_aliasy if a not in istniejace]
        row.aliasy.extend(ProductAliasModel(alias_text=a) for a in dopisane)
        wyniki.append(f"{fragment_kodu}: dopisane aliasy {dopisane if dopisane else '(brak - juz istnialy)'}")

    session.commit()
    return "\n".join(wyniki)


def main() -> None:
    session = SessionLocal()
    try:
        wynik = uzupelnij(session)
    finally:
        session.close()
    print(wynik)


if __name__ == "__main__":
    main()
