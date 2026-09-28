"""Retencja zakonczonych analiz i odpowiadajacych im plikow w storage."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session, selectinload

# Rejestracja tabel wskazywanych przez klucze obce jest wymagana takze w samodzielnym CLI,
# ktore (w przeciwienstwie do FastAPI) nie importuje automatycznie modulow users/products.
from app.modules.products.models import ProductModel as _ProductModel  # noqa: F401
from app.modules.users.models import UserModel as _UserModel  # noqa: F401

from .models import DocumentModel, DocumentReportModel
from .storage import FileStorage

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("done", "error")
_OPEN_REPORT_STATUS = "open"


def prune_documents(session: Session, storage: FileStorage, *, limit: int) -> int:
    """Usun zakonczone dokumenty starsze niz ``limit`` najnowszych analiz.

    Limit dotyczy calej historii, a nie liczby pojedynczych stron. Dokumenty aktywne
    (``queued``/``processing``) nigdy nie sa kandydatami do usuniecia - tak samo dokumenty z
    NIEROZWIAZANYM zgloszeniem problemu (2026-09-28, na zyczenie uzytkownika: zgloszenie
    pracownika musi zostac dostepne do rozwiazania, niezaleznie od tego jak stary jest dokument;
    po oznaczeniu zgloszenia jako rozwiazane dokument znow jest normalnym kandydatem). Blokada
    wierszy chroni przed rownoleglym sprzataniem przez kilka procesow workera.

    Kazdy dokument jest usuwany (plik + wiersz) i zatwierdzany OSOBNO - naprawa bledu wykrytego
    na produkcji 2026-09-28: usuwanie CALEJ paczki w jednej transakcji oznaczalo, ze jeden
    dokument z nieprzewidzianym konfliktem (np. brakujaca kaskada dla powiazanej tabeli) wybijal
    WSZYSTKIE wczesniejsze, poprawne usuniecia w tej samej paczce (wyjatek lapany w tasks.py
    dopiero na samej gorze, session.rollback() kasowal caly postep) - retencja przez to po cichu
    nie usuwala NIC, nigdy, odkad zostala wdrozona."""
    if limit < 1:
        logger.warning("Retencja pominieta: document_retention_limit musi byc dodatni")
        return 0

    keep_ids = [
        row[0]
        for row in (
            session.query(DocumentModel.id)
            .order_by(DocumentModel.created_at.desc(), DocumentModel.id.desc())
            .limit(limit)
            .all()
        )
    ]
    open_report_ids = {
        row[0]
        for row in (
            session.query(DocumentReportModel.document_id)
            .filter(DocumentReportModel.status == _OPEN_REPORT_STATUS)
            .distinct()
            .all()
        )
    }

    query = (
        session.query(DocumentModel)
        .options(selectinload(DocumentModel.extra_files), selectinload(DocumentModel.items))
        .filter(DocumentModel.status.in_(_TERMINAL_STATUSES))
        .order_by(DocumentModel.created_at.asc(), DocumentModel.id.asc())
        .with_for_update(skip_locked=True)
    )
    if keep_ids:
        query = query.filter(~DocumentModel.id.in_(keep_ids))
    if open_report_ids:
        query = query.filter(~DocumentModel.id.in_(open_report_ids))

    removed = 0
    for document in query.all():
        keys = [document.file_key, *(extra.file_key for extra in document.extra_files)]
        try:
            for key in keys:
                storage.delete(key)
            session.delete(document)
            session.commit()
        except Exception:
            # Ani plik, ani wiersz tego JEDNEGO dokumentu nie zostaja usuniete - ale reszta
            # paczki (juz zatwierdzona osobno, wyzej w petli) zostaje. Ponowne wywolanie jest
            # bezpieczne, bo S3 DeleteObject jest idempotentne.
            session.rollback()
            logger.exception(
                "Retencja: nie udalo sie usunac dokumentu",
                extra={"document_id": str(document.id)},
            )
            continue
        removed += 1

    if removed:
        logger.info("Retencja: usunieto stare analizy", extra={"removed": removed, "limit": limit})
    return removed
