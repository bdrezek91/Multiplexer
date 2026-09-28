"""Jednorazowa korekta danych: dopisuje alias dla juz istniejacego produktu "Różnicówka niemiecka
CDS240D" (2026-09-28, na zyczenie uzytkownika) - patrz scripts/uzupelnij_cds263d.py dla
analogicznego, wczesniejszego przypadku (CDS263D).

Produkt JUZ ISTNIEJE w katalogu z aliasem "Różnicówka niemiecka CDS240D" (dziala tylko gdy OCR
odczyta sam kod). Odreczny opis z formularza bez kodu ("różnicówka niemiecka 1 fazowa 40A") NIE
jest dokladnym wierszem formularza (roznica cyfry fazy vs "3 fazowa 40A"), wiec trafia do
recznej weryfikacji - a samo dopasowanie tekstowe do "Różnicówka niemiecka CDS240D" wychodzi
ponizej progu zaufania (kod produktu w nazwie nie wystepuje w tekscie z kartki), wiec mimo
poprawnego wyboru caly czas jest oznaczane na czerwono.

Alias "niemiecka 40a" (BEZ wymogu slowa "1"/"fazowa") jest celowo krotki i ogolny - w praktyce
"1-fazowa" jest domyslnym, nienazwanym wprost wariantem (tylko wariant 3-fazowy jest zwykle
jawnie opisywany), a alias "różnicówka niemiecka 3 fazowa 40a" na CDC440J (5 tokenow) i tak
wygrywa specyficznoscia, gdy slowo "3"/"fazowa" faktycznie wystapi w tekscie - patrz
matcher/shared.py: alias_hits().

Uzycie:
    docker compose -f docker-compose.prod.yml exec backend python -m scripts.uzupelnij_cds240d
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

NOWE_ALIASY = ["różnicówka niemiecka 1 fazowa 40a", "niemiecka 40a"]
BRAKUJACE_ATRYBUTY = {
    "prad_A": 40,
    "liczba_faz": 1,
    "standard_gniazda": "DE",
}


def uzupelnij(session: Session) -> str:
    row = (
        session.query(ProductModel)
        .options(selectinload(ProductModel.aliasy))
        .filter(ProductModel.dzial == "elektryka", ProductModel.kod.ilike("%CDS240D%"))
        .first()
    )
    if row is None:
        return "Nie znaleziono produktu z kodem zawierajacym 'CDS240D' w dziale elektryka - nic nie zmieniono."

    atrybuty = dict(row.atrybuty or {})
    zmienione = []
    for klucz, wartosc in BRAKUJACE_ATRYBUTY.items():
        if atrybuty.get(klucz) is None:
            atrybuty[klucz] = wartosc
            zmienione.append(f"{klucz}={wartosc}")
    row.atrybuty = atrybuty

    istniejace_aliasy = {a.alias_text for a in row.aliasy}
    dopisane = [a for a in NOWE_ALIASY if a not in istniejace_aliasy]
    row.aliasy.extend(ProductAliasModel(alias_text=a) for a in dopisane)

    session.commit()

    opis = [f"Produkt: {row.kod!r}"]
    opis.append(f"Uzupelnione atrybuty: {', '.join(zmienione) if zmienione else '(brak - juz byly ustawione)'}")
    opis.append(f"Dopisane aliasy: {dopisane if dopisane else '(brak - juz istnialy)'}")
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
