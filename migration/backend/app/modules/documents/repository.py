"""Repozytorium Document/DocumentItem (Etap 7)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .models import DocumentItemModel, DocumentModel


class DocumentNotFoundError(Exception):
    def __init__(self, document_id):
        self.document_id = document_id
        super().__init__(f"Dokument {document_id!r} nie istnieje")


def _to_uuid(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def create_document(
    session: Session,
    *,
    user_id,
    file_key: str,
    mime: str,
    original_filename: str,
    magazyn: Optional[str] = None,
    source_type: str = "ai_scan",
    document_id: Optional[uuid.UUID] = None,
) -> DocumentModel:
    kwargs = {"id": document_id} if document_id is not None else {}
    document = DocumentModel(
        **kwargs,
        user_id=user_id, file_key=file_key, mime=mime, original_filename=original_filename,
        magazyn=magazyn, source_type=source_type, status="queued",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def get_document(session: Session, document_id) -> Optional[DocumentModel]:
    uid = _to_uuid(document_id)
    if uid is None:
        return None
    return (
        session.query(DocumentModel)
        .options(selectinload(DocumentModel.items))
        .filter(DocumentModel.id == uid)
        .first()
    )


def list_documents(session: Session, *, user_id=None, limit: int = 50, offset: int = 0) -> list[DocumentModel]:
    query = session.query(DocumentModel).options(selectinload(DocumentModel.items))
    if user_id is not None:
        query = query.filter(DocumentModel.user_id == user_id)
    return query.order_by(DocumentModel.created_at.desc()).offset(offset).limit(limit).all()


def mark_processing(session: Session, document: DocumentModel) -> None:
    document.status = "processing"
    session.commit()


def mark_done(
    session: Session,
    document: DocumentModel,
    *,
    numer_projektu: Optional[str],
    used_provider: str,
    rejected_count: int,
    items: list[dict],
) -> None:
    document.numer_projektu = numer_projektu
    document.used_provider = used_provider
    document.rejected_count = rejected_count
    document.items = [DocumentItemModel(**item) for item in items]
    document.status = "done"
    document.error_message = None
    session.commit()


def mark_error(session: Session, document: DocumentModel, error_message: str) -> None:
    document.status = "error"
    document.error_message = error_message[:2000]
    session.commit()
