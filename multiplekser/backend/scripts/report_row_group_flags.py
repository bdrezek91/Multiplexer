"""Raport skutecznosci drugiej, niezaleznej kontroli AI dla grup podobnych wierszy formularza
(2026-09-17, na zyczenie uzytkownika - patrz ocr/verify.py: verify_row_group_alignment,
documents/tasks.py: _check_row_group_alignment).

Kazdy wpis w tabeli `ocr_row_group_flag` to jeden przypadek, w ktorym druga kontrola NIE
zgadzala sie z glownym odczytem (zgodnosc, najczestszy przypadek, nie generuje wpisu - patrz
repository.py: log_row_group_flag). Ten skrypt laczy kazdy wpis z AKTUALNYM stanem
odpowiadajacej mu pozycji dokumentu (po `document_id` + `rozpoznana_nazwa`), zeby oszacowac
"skutecznosc": czy operator faktycznie POPRAWIL ta pozycje po fakcie (ilosc_finalna inna niz w
momencie oflagowania) - to sygnal, ze flaga byla trafna, nie szumem.

UWAGA: to przyblizenie, nie pewnik - operator mogl tez zmienic ilosc_finalna z innego powodu
(albo NIE zmienic, mimo ze flaga byla trafna, jesli po prostu nie zauwazyl). Traktuj wynik jako
wskazowke do dalszej obserwacji, nie ostateczny werdykt.

Uzycie:
    python -m scripts.report_row_group_flags [--dni N]
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.modules.documents.models import DocumentItemModel, OcrRowGroupFlagModel


def _looks_corrected(flag: OcrRowGroupFlagModel, session: Session) -> bool | None:
    """None = nie da sie ustalic (pozycja zostala usunieta/dokument skasowany).

    "mismatch_existing" - pozycja juz istniala przy oflagowaniu; poprawiona = ilosc_finalna
    zmieniona od tamtej pory. "missing_flagged_group" - NIC nie zostalo dodane automatycznie
    (patrz tasks.py); poprawiona = uzytkownik reczne dodal pozycje o tej nazwie po fakcie."""
    item = (
        session.query(DocumentItemModel)
        .filter(
            DocumentItemModel.document_id == flag.document_id,
            DocumentItemModel.rozpoznana_nazwa == flag.rozpoznana_nazwa,
        )
        .first()
    )
    if flag.kind == "missing_flagged_group":
        return item is not None  # brak pozycji przy zapisie flagi -> pojawienie sie = korekta
    if item is None:
        return None
    return item.ilosc_finalna != flag.main_ilosc_wydana


def build_report(session: Session, since: datetime) -> str:
    flags = (
        session.query(OcrRowGroupFlagModel)
        .filter(OcrRowGroupFlagModel.created_at >= since)
        .order_by(OcrRowGroupFlagModel.created_at.desc())
        .all()
    )
    if not flags:
        return f"Brak zdarzen drugiej kontroli AI (grupy podobnych wierszy) od {since.date()}."

    by_kind = Counter(f.kind for f in flags)
    by_label = Counter(f.rozpoznana_nazwa for f in flags)
    by_dzial = Counter(f.dzial for f in flags)

    corrected = 0
    unknown = 0
    for flag in flags:
        result = _looks_corrected(flag, session)
        if result is None:
            unknown += 1
        elif result:
            corrected += 1

    lines = [
        f"Raport drugiej kontroli AI (grupy podobnych wierszy) - od {since.date()} do dziś",
        f"Łącznie zdarzeń: {len(flags)}",
        f"  - mismatch_existing (oflagowana istniejąca pozycja): {by_kind.get('mismatch_existing', 0)}",
        f"  - missing_flagged_group (sugerowana pominięta pozycja, nie dodana automatycznie): "
        f"{by_kind.get('missing_flagged_group', 0)}",
        "",
        f"Wygląda na poprawione przez operatora: {corrected}/{len(flags) - unknown} "
        f"(pominięto {unknown} bez ustalonego stanu - pozycja/dokument usunięty)",
        "",
        "Najczęściej flagowane etykiety:",
    ]
    for label, count in by_label.most_common(10):
        lines.append(f"  {count:3d}x  {label}")
    lines.append("")
    lines.append("Wg działu:")
    for dzial, count in by_dzial.most_common():
        lines.append(f"  {dzial}: {count}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dni", type=int, default=30, help="Liczba dni wstecz (domyślnie 30).")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.dni)
    session = SessionLocal()
    try:
        print(build_report(session, since))
    finally:
        session.close()


if __name__ == "__main__":
    main()
