"""Retencja zakonczonych analiz i odpowiadajacych im plikow w storage."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session, selectinload

from .models import DocumentModel
from .storage import FileStorage

logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = ("done", "error")


def prune_documents(session: Session, storage: FileStorage, *, limit: int) -> int:
    """Usun zakonczone dokumenty starsze niz ``limit`` najnowszych analiz.

    Limit dotyczy calej historii, a nie liczby pojedynczych stron. Dokumenty aktywne
    (``queued``/``processing``) nigdy nie sa kandydatami do usuniecia. Blokada wierszy chroni
    przed rownoleglym sprzataniem przez kilka procesow workera.
    """
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
    query = (
        session.query(DocumentModel)
        .options(selectinload(DocumentModel.extra_files), selectinload(DocumentModel.items))
        .filter(DocumentModel.status.in_(_TERMINAL_STATUSES))
        .order_by(DocumentModel.created_at.asc(), DocumentModel.id.asc())
        .with_for_update(skip_locked=True)
    )
    if keep_ids:
        query = query.filter(~DocumentModel.id.in_(keep_ids))

    removed = 0
    for document in query.all():
        keys = [document.file_key, *(extra.file_key for extra in document.extra_files)]
        try:
            for key in keys:
                storage.delete(key)
        except Exception:
            # Nie usuwamy rekordu z bazy, jesli nie udalo sie posprzatac storage. Ponowne
            # wywolanie jest bezpieczne, bo S3 DeleteObject jest idempotentne.
            logger.exception(
                "Retencja: nie udalo sie usunac plikow dokumentu",
                extra={"document_id": str(document.id)},
            )
            continue
        session.delete(document)
        removed += 1

    session.commit()
    if removed:
        logger.info("Retencja: usunieto stare analizy", extra={"removed": removed, "limit": limit})
    return removed
