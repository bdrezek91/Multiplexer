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
    nie usuwala NIC, nigdy, odkad zostala wdrozona.

    KOLEJNOSC jest celowa i wazna (2026-09-28, druga czesc tej samej naprawy): NAJPIERW kasujemy
    wiersz w bazie i dopiero PO potwierdzonym commicie kasujemy plik ze storage - nigdy odwrotnie.
    Storage (S3/MinIO) nie jest transakcyjny wzgledem Postgresa - usuniecie pliku jest
    nieodwracalne, a DELETE FROM document moze sie nie udac (np. przez nieprzewidzianą kaskadę).
    Stary kod kasowal PLIK przed commitem wiersza - gdy commit wybuchal (co dzialo sie ZA KAZDYM
    razem odkad w paczce pojawil sie pierwszy dokument ze zgloszeniem/logiem AI), plik znikal
    bezpowrotnie, a wiersz zostawal - to faktyczna przyczyna dokumentow z bledem "nie znaleziono
    w storage" na produkcji (nie restart/reset wolumenu, jak wczesniej podejrzewano - sam
    poprzedni blad retencji). Kolejnosc "wiersz najpierw" gwarantuje, ze w najgorszym razie
    zostaje NIEUZYWANY plik do posprzatania recznie - nigdy odwrotnie (dzialajacy dokument bez
    pliku)."""
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
            session.delete(document)
            session.commit()
        except Exception:
            # Wiersz NIE zostal usuniety - plik zostaje niedotkniety, dokument po prostu wraca
            # jako kandydat przy nastepnym uruchomieniu. Bezpieczny stan: dzialajacy dokument.
            session.rollback()
            logger.exception(
                "Retencja: nie udalo sie usunac wiersza dokumentu - plik pozostawiony",
                extra={"document_id": str(document.id)},
            )
            continue
        for key in keys:
            try:
                storage.delete(key)
            except Exception:
                # Wiersz juz nie istnieje - plik zostaje osierocony w storage (do recznego
                # sprzatania), ale to nieszkodliwy stan (dokumentu i tak juz nie ma w UI).
                # Ponowne wywolanie bezpieczne, bo S3 DeleteObject jest idempotentne.
                logger.exception(
                    "Retencja: wiersz dokumentu usuniety, ale nie udalo sie usunac pliku ze storage",
                    extra={"document_id": str(document.id), "key": key},
                )
        removed += 1

    if removed:
        logger.info("Retencja: usunieto stare analizy", extra={"removed": removed, "limit": limit})
    return removed
