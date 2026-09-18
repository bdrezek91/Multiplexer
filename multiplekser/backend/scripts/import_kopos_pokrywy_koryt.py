"""Dodaje do katalogu (Elektryka) korytko czarne 40x40 (90 stopni) oraz 12 pokryw KOPOS do
korytek LHD 40x20/40x40 (2026-09-18, na zyczenie uzytkownika - kod produktu zeskanowany na
formularzu jako odreczny dopisek w polu "INNE", patrz historia czatu: "NAROŻNIK DO KORYT
8635/HF" -> KOPOS POKRYWA NAROŻNA WEWN. (LHD 40X20) 8635 FB).

KORYTKO CZARNE 40X20 (90 STOPNI) juz istnieje w katalogu (patrz fixtures/baza_elektryka.json) -
40X40 to analogiczny, brakujacy odpowiednik. Pokrywy KOPOS sa calkowicie nowym asortymentem.

Kazdy produkt dostaje 2-tokenowy alias {ksztalt} {kod_kopos} (np. "naroznik 8635") - to
WYSTARCZY do jednoznacznego trafienia przez alias_hits() (matcher/shared.py: wszystkie tokeny
aliasu musza byc podzbiorem tokenow zapytania), niezaleznie od tego czy na formularzu jest pelna
nazwa "NAROŻNIK DO KORYT" czy skrocona - jedynym warunkiem jest poprawnie odczytany 4-cyfrowy
kod. OCR bledow w samym kodzie (np. odreczne "6" odczytane jako "8") ten alias nie naprawi -
to wymaga recznej korekty pola "Dopasowany kod" na dokumencie.

Idempotentny: klucz naturalny to (kod, dzial="elektryka"). Istniejacy produkt NIE jest
nadpisywany (nazwa/jm/grupa) - dopisywane sa tylko brakujace aliasy, zeby nie nadpisac reczych
korekt juz wprowadzonych w produkcyjnym katalogu.

Uzycie:
    python -m scripts.import_kopos_pokrywy_koryt
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.products.models import ProductAliasModel, ProductModel

GRUPA = "Trasy kablowe i mocowania"
DZIAL = "elektryka"

# (kod, nazwa, jm, wymiar_mm, aliasy)
PRODUCTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "KORYTKO CZARNE 40X40 (90 STOPNI)", "Korytko czarne 40x40 (90 stopni)", "M", "40x40",
        ["90 stopni 40x40"],
    ),
    (
        "KOPOS POKRYWA KĄTOWA (LHD 40X20) 8633 FB", "Kopos pokrywa kątowa (LHD 40x20) 8633 FB", "SZT", "40x20",
        ["katowa 8633", "pokrywa katowa 8633"],
    ),
    (
        "KOPOS POKRYWA KĄTOWA (LHD 40X40) 8643 FB", "Kopos pokrywa kątowa (LHD 40x40) 8643 FB", "SZT", "40x40",
        ["katowa 8643", "pokrywa katowa 8643"],
    ),
    (
        "KOPOS POKRYWA KOŃCOWA (LHD 40X20) 8631 FB", "Kopos pokrywa końcowa (LHD 40x20) 8631 FB", "SZT", "40x20",
        ["zakonczenie 8631", "koncowa 8631", "pokrywa koncowa 8631"],
    ),
    (
        "KOPOS POKRYWA KOŃCOWA (LHD 40X40) 8641 FB", "Kopos pokrywa końcowa (LHD 40x40) 8641 FB", "SZT", "40x40",
        ["zakonczenie 8641", "koncowa 8641", "pokrywa koncowa 8641"],
    ),
    (
        "KOPOS POKRYWA ŁĄCZĄCA (LHD 40X20) 8632 FB", "Kopos pokrywa łącząca (LHD 40x20) 8632 FB", "SZT", "40x20",
        ["lacznik 8632", "laczaca 8632", "pokrywa laczaca 8632"],
    ),
    (
        "KOPOS POKRYWA ŁĄCZĄCA (LHD 40X40) 8642 FB", "Kopos pokrywa łącząca (LHD 40x40) 8642 FB", "SZT", "40x40",
        ["lacznik 8642", "laczaca 8642", "pokrywa laczaca 8642"],
    ),
    (
        "KOPOS POKRYWA NAROŻNA WEWN. (LHD 40X20) 8635 FB", "Kopos pokrywa narożna wewn. (LHD 40x20) 8635 FB", "SZT", "40x20",
        ["naroznik 8635", "narozna 8635", "pokrywa narozna 8635"],
    ),
    (
        "KOPOS POKRYWA NAROŻNA WEWN. (LHD 40X40) 8645 FB", "Kopos pokrywa narożna wewn. (LHD 40x40) 8645 FB", "SZT", "40x40",
        ["naroznik 8645", "narozna 8645", "pokrywa narozna 8645"],
    ),
    (
        "KOPOS POKRYWA NAROŻNA ZEWN. (LHD 40X20) 8636 FB", "Kopos pokrywa narożna zewn. (LHD 40x20) 8636 FB", "SZT", "40x20",
        ["naroznik 8636", "narozna 8636", "pokrywa narozna 8636"],
    ),
    (
        "KOPOS POKRYWA NAROŻNA ZEWN. (LHD 40X40) 8646 FB", "Kopos pokrywa narożna zewn. (LHD 40x40) 8646 FB", "SZT", "40x40",
        ["naroznik 8646", "narozna 8646", "pokrywa narozna 8646"],
    ),
    (
        "KOPOS POKRYWA ODGAŁĘŹNA (LHD 40X20) 8634 FB", "Kopos pokrywa odgałęźna (LHD 40x20) 8634 FB", "SZT", "40x20",
        ["odgalezna 8634", "pokrywa odgalezna 8634"],
    ),
    (
        "KOPOS POKRYWA ODGAŁĘŹNA (LHD 40X40) 8644 FB", "Kopos pokrywa odgałęźna (LHD 40x40) 8644 FB", "SZT", "40x40",
        ["odgalezna 8644", "pokrywa odgalezna 8644"],
    ),
]


def import_kopos_pokrywy_koryt(session: Session) -> dict[str, int]:
    stats = {"utworzone": 0, "aliasy_dopisane": 0, "bez_zmian": 0}
    existing = {
        row.kod: row
        for row in session.query(ProductModel).filter(ProductModel.dzial == DZIAL).all()
    }

    for kod, nazwa, jm, wymiar_mm, aliasy in PRODUCTS:
        row = existing.get(kod)
        if row is None:
            row = ProductModel(
                kod=kod, nazwa=nazwa, jm=jm, grupa=GRUPA, dzial=DZIAL,
                status="generyczny", atrybuty={"kolor": "CZARNY", "wymiar_mm": wymiar_mm},
            )
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
        stats = import_kopos_pokrywy_koryt(session)
    finally:
        session.close()

    print(
        f"Import pokryw KOPOS zakonczony: {stats['utworzone']} utworzonych produktow, "
        f"{stats['aliasy_dopisane']} dopisanych aliasow, {stats['bez_zmian']} bez zmian."
    )


if __name__ == "__main__":
    main()
