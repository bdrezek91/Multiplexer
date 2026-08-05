"""Repozytorium Document/DocumentItem (Etap 7)."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from .models import DocumentFileModel, DocumentItemModel, DocumentModel


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
    extra_files: Optional[list[tuple[str, str]]] = None,
) -> DocumentModel:
    """`extra_files` - lista (file_key, mime) dla strony 2+ dokumentu wieloplikowego (np. drugie
    zdjecie z telefonu tej samej papierowej wydawki, patrz historia czatu) - pierwsza strona
    zawsze idzie do file_key/mime powyzej, `extra_files` jest zwykle puste (pojedynczy
    plik/PDF - dotychczasowy, najczestszy przypadek)."""
    kwargs = {"id": document_id} if document_id is not None else {}
    document = DocumentModel(
        **kwargs,
        user_id=user_id, file_key=file_key, mime=mime, original_filename=original_filename,
        magazyn=magazyn, source_type=source_type, status="queued",
        extra_files=[
            DocumentFileModel(sequence=i, file_key=fk, mime=fm)
            for i, (fk, fm) in enumerate(extra_files or [])
        ],
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
        .options(selectinload(DocumentModel.items), selectinload(DocumentModel.extra_files))
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
    document.ai_trace = []
    session.commit()


def append_ai_trace_event(
    session: Session, document: DocumentModel, event: dict[str, object], *, max_events: int = 200,
) -> None:
    """Dopisuje zdarzenie widoczne w UI i od razu je zatwierdza, aby polling strony pokazal
    postep jeszcze podczas trwajacego OCR. Lista ma limit, zeby uszkodzony dokument/retry nie
    powiekszal rekordu bez konca. Przypisanie nowej listy zapewnia wykrycie zmiany JSONB przez
    SQLAlchemy bez MutableList."""
    trace = list(document.ai_trace or [])
    trace.append(event)
    document.ai_trace = trace[-max_events:]
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


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
    document.items = [DocumentItemModel(sequence=i, **item) for i, item in enumerate(items)]
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
    match_quality: str = ...,
    match_score: float = ...,
    matched_product_id=...,
    commit: bool = True,
) -> DocumentItemModel:
    """Ellipsis jako "nie zmieniaj tego pola" - odroznia "brak zmiany" od "ustaw na None"
    (np. usuniecie recznej korekty kodu). `commit=False` pozwala wywolujacemu zebrac wiele
    zmian pozycji jednego dokumentu w jedna transakcje (patrz rematch_items ponizej)."""
    if ilosc_finalna is not ...:
        item.ilosc_finalna = ilosc_finalna
    if match_kod is not ...:
        item.match_kod = match_kod
    if match_nazwa is not ...:
        item.match_nazwa = match_nazwa
    if match_jm is not ...:
        item.match_jm = match_jm
    if match_quality is not ...:
        item.match_quality = match_quality
    if match_score is not ...:
        item.match_score = match_score
    if matched_product_id is not ...:
        item.matched_product_id = matched_product_id
    if commit:
        session.commit()
        session.refresh(item)
    return item


def set_magazyn(session: Session, document: DocumentModel, magazyn: Optional[str]) -> None:
    document.magazyn = magazyn
    session.commit()


def add_manual_item(
    session: Session,
    document: DocumentModel,
    *,
    rozpoznana_nazwa: str,
    match_kod: str,
    match_nazwa: str,
    match_jm: str,
    matched_product_id,
    ilosc_finalna: float,
) -> DocumentItemModel:
    """Reczne dodanie pozycji spoza OCR (patrz DocumentItemAddIn) - `sequence` na koncu
    istniejacych pozycji (uzywane wprost jako kolejnosc wyniku dla Hydrauliki, patrz
    generator/core_hydraulika.py; Elektryka i tak sortuje fizycznie przy generowaniu/podgladzie,
    patrz router._items_in_physical_order). Dopasowanie od razu "ok" (uzytkownik wybral wprost
    z katalogu, nie ma tu niepewnosci automatycznego dopasowania do rozstrzygniecia)."""
    next_sequence = max((it.sequence for it in document.items), default=-1) + 1
    item = DocumentItemModel(
        document_id=document.id,
        sequence=next_sequence,
        rozpoznana_nazwa=rozpoznana_nazwa,
        ilosc_wydana=None,
        ilosc_zuzyta=None,
        ilosc_finalna=ilosc_finalna,
        matched_product_id=matched_product_id,
        match_kod=match_kod,
        match_nazwa=match_nazwa,
        match_jm=match_jm,
        match_quality="ok",
        match_score=1.0,
        off_form=False,
        needs_review=False,
        form_note="",
        uwagi="Dodano ręcznie",
        confidence=None,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
