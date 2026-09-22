"""Jednorazowa korekta danych: dopisuje brakujace atrybuty rozpoznawania (kraj/prad/faza) i
alias dla juz istniejacego produktu "Wylacznik roznicoopradowy 2P CDS263D" (2026-09-22, na
zyczenie uzytkownika: na kartce napisane "roznicowka niemiecka 1 fazowa 63A", bez podania kodu
CDS263D wprost).

Produkt JUZ ISTNIEJE w katalogu z aliasem "Różnicówka niemiecka CDS263D" (dziala tylko gdy OCR
odczyta sam kod), ale bez atrybutow prad_A/liczba_faz/standard_gniazda - w przeciwienstwie do
siostrzanego produktu "RÓŻNICÓWKA POLSKA 3 FAZOWA 40A (CDC440J)", ktory ma je ustawione.
Bez tych atrybutow ogolne dopasowanie fuzzy (bez alias-hitu) mogloby przegrac z innym wariantem
"niemieckim" majacym ustawiony standard_gniazda='DE' (mniej brakujacych atrybutow = wyzszy
priorytet w tie-breaku matchera - patrz matcher/core_elektryka.py).

Szuka produktu po FRAGMENCIE kodu ("CDS263D"), nie po dokladnym stringu - w bazie kod moze miec
inne bialе znaki niz w lokalnym fixture. Nie nadpisuje juz ustawionych atrybutow - tylko
uzupelnia braki (None) i dopisuje alias, jesli go jeszcze nie ma.

Uzycie:
    docker compose -f docker-compose.prod.yml exec backend python -m scripts.uzupelnij_cds263d
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

NOWY_ALIAS = "różnicówka niemiecka 1 fazowa 63A"
BRAKUJACE_ATRYBUTY = {
    "prad_A": 63,
    "liczba_faz": 1,
    "standard_gniazda": "DE",
}


def uzupelnij(session: Session) -> str:
    row = (
        session.query(ProductModel)
        .options(selectinload(ProductModel.aliasy))
        .filter(ProductModel.dzial == "elektryka", ProductModel.kod.ilike("%CDS263D%"))
        .first()
    )
    if row is None:
        return "Nie znaleziono produktu z kodem zawierajacym 'CDS263D' w dziale elektryka - nic nie zmieniono."

    atrybuty = dict(row.atrybuty or {})
    zmienione = []
    for klucz, wartosc in BRAKUJACE_ATRYBUTY.items():
        if atrybuty.get(klucz) is None:
            atrybuty[klucz] = wartosc
            zmienione.append(f"{klucz}={wartosc}")
    row.atrybuty = atrybuty

    istniejace_aliasy = {a.alias_text for a in row.aliasy}
    dopisano_alias = False
    if NOWY_ALIAS not in istniejace_aliasy:
        row.aliasy.append(ProductAliasModel(alias_text=NOWY_ALIAS))
        dopisano_alias = True

    session.commit()

    opis = [f"Produkt: {row.kod!r}"]
    opis.append(f"Uzupelnione atrybuty: {', '.join(zmienione) if zmienione else '(brak - juz byly ustawione)'}")
    opis.append(f"Alias {NOWY_ALIAS!r}: {'dopisany' if dopisano_alias else 'juz istnial'}")
    return "\n".join(opis)


def main() -> None:
    session = SessionLocal()
    try:
        wynik = uzupelnij(session)
    finally:
        session.close()
    print(wynik)


if __name__ == "__main__":
    main()
