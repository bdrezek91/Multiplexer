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
    dzial: Optional[str] = None,
    dzial_confidence: Optional[float] = None,
) -> None:
    document.numer_projektu = numer_projektu
    document.used_provider = used_provider
    document.rejected_count = rejected_count
    document.items = [DocumentItemModel(**item) for item in items]
    document.status = "done"
    document.error_message = None
    document.dzial = dzial
    document.dzial_confidence = dzial_confidence
    session.commit()


def mark_error(session: Session, document: DocumentModel, error_message: str) -> None:
    document.status = "error"
    document.error_message = error_message[:2000]
    session.commit()


def get_item(session: Session, document_id, item_id) -> Optional[DocumentItemModel]:
    doc_uid, item_uid = _to_uuid(document_id), _to_uuid(item_id)
    if doc_uid is None or item_uid is None:
        return None
    return (
        session.query(DocumentItemModel)
        .filter(DocumentItemModel.id == item_uid, DocumentItemModel.document_id == doc_uid)
        .first()
    )


def update_item(
    session: Session,
    item: DocumentItemModel,
    *,
    ilosc_finalna: Optional[float] = ...,
    match_kod: Optional[str] = ...,
    match_nazwa: Optional[str] = ...,
    match_jm: Optional[str] = ...,
    matched_product_id=...,
) -> DocumentItemModel:
    """Ellipsis jako "nie zmieniaj tego pola" - odroznia "brak zmiany" od "ustaw na None"
    (np. usuniecie recznej korekty kodu)."""
    if ilosc_finalna is not ...:
        item.ilosc_finalna = ilosc_finalna
    if match_kod is not ...:
        item.match_kod = match_kod
    if match_nazwa is not ...:
        item.match_nazwa = match_nazwa
    if match_jm is not ...:
        item.match_jm = match_jm
    if matched_product_id is not ...:
        item.matched_product_id = matched_product_id
    session.commit()
    session.refresh(item)
    return item
