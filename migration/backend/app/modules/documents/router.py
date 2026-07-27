"""Endpoint dokumentow (Etap 7) - ASYNCHRONICZNY nastepca /ocr/recognize z Etapu 6 (usuniety -
byl swiadomie oznaczony jako ryzyko: blokowal request HTTP do 90s, zamiast kolejki w tle).

POST /documents zapisuje plik do storage, tworzy rekord Document (status "queued") i zleca
przetwarzanie Celery - odpowiada natychmiast (202). GET /documents/{id} pozwala odpytac status
i (po zakonczeniu) wynik. Wlasciciel dokumentu lub admin - inni dostaja 403 (patrz test RBAC).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.users import get_current_user
from app.modules.users.deps import check_magazyn_access
from app.modules.users.models import UserModel

from . import repository
from .models import DocumentModel
from .schemas import DocumentCreatedOut, DocumentItemOut, DocumentOut
from .storage import get_storage
from .tasks import process_ocr_document

router = APIRouter(prefix="/documents", tags=["documents"])

_PDF_MIME = "application/pdf"


def _to_schema(document: DocumentModel) -> DocumentOut:
    return DocumentOut(
        id=str(document.id),
        status=document.status,
        numer_projektu=document.numer_projektu,
        source_type=document.source_type,
        magazyn=document.magazyn,
        original_filename=document.original_filename,
        used_provider=document.used_provider,
        rejected_count=document.rejected_count,
        error_message=document.error_message,
        created_at=document.created_at,
        items=[
            DocumentItemOut(
                id=str(it.id),
                rozpoznana_nazwa=it.rozpoznana_nazwa,
                ilosc_wydana=it.ilosc_wydana,
                ilosc_zuzyta=it.ilosc_zuzyta,
                ilosc_finalna=it.ilosc_finalna,
                match_kod=it.match_kod,
                match_nazwa=it.match_nazwa,
                match_jm=it.match_jm,
                match_quality=it.match_quality,
                match_score=it.match_score,
                off_form=it.off_form,
                needs_review=it.needs_review,
                form_note=it.form_note,
                uwagi=it.uwagi,
                confidence=it.confidence,
            )
            for it in document.items
        ],
    )


def _check_owner_or_admin(document: DocumentModel, user: UserModel) -> None:
    if user.rola != "admin" and document.user_id != user.id:
        raise HTTPException(status_code=403, detail="Brak dostepu do tego dokumentu")


@router.post("", response_model=DocumentCreatedOut, status_code=202)
async def create_document(
    plik: UploadFile = File(...),
    magazyn: str | None = Form(default=None),
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    check_magazyn_access(user, magazyn)

    raw = await plik.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Pusty plik")

    is_pdf = plik.content_type == _PDF_MIME or (plik.filename or "").lower().endswith(".pdf")
    mime = _PDF_MIME if is_pdf else (plik.content_type or "application/octet-stream")

    document_id = uuid.uuid4()
    file_key = f"documents/{document_id}/{plik.filename or 'plik'}"
    get_storage().upload(file_key, raw, mime)

    document = repository.create_document(
        session, document_id=document_id, user_id=user.id, file_key=file_key, mime=mime,
        original_filename=plik.filename or "plik", magazyn=magazyn,
    )

    process_ocr_document.delay(str(document.id))

    return DocumentCreatedOut(id=str(document.id), status=document.status)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    owner_filter = None if user.rola == "admin" else user.id
    documents = repository.list_documents(session, user_id=owner_filter)
    return [_to_schema(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: str,
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    document = repository.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Dokument {document_id!r} nie istnieje")
    _check_owner_or_admin(document, user)
    return _to_schema(document)
