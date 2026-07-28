"""Endpoint dokumentow (Etap 7) - ASYNCHRONICZNY nastepca /ocr/recognize z Etapu 6 (usuniety -
byl swiadomie oznaczony jako ryzyko: blokowal request HTTP do 90s, zamiast kolejki w tle).

POST /documents zapisuje plik do storage, tworzy rekord Document (status "queued") i zleca
przetwarzanie Celery - odpowiada natychmiast (202). GET /documents/{id} pozwala odpytac status
i (po zakonczeniu) wynik. Wlasciciel dokumentu lub admin - inni dostaja 403 (patrz test RBAC).
"""
from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.generator import GeneratorItem, encode_cp1250, generate_output, get_filename, physical_order_for
from app.modules.matcher import rules_from_db
from app.modules.products import Catalog
from app.modules.products.models import ProductModel
from app.modules.users import get_current_user
from app.modules.users.deps import check_magazyn_access
from app.modules.users.models import UserModel

from . import repository
from .models import DocumentItemModel, DocumentModel
from .schemas import DocumentCreatedOut, DocumentItemOut, DocumentItemUpdateIn, DocumentOut, GenerateRequest
from .storage import get_storage
from .tasks import process_ocr_document

router = APIRouter(prefix="/documents", tags=["documents"])

_PDF_MIME = "application/pdf"


def _item_to_schema(it: DocumentItemModel) -> DocumentItemOut:
    return DocumentItemOut(
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


def _items_in_physical_order(document: DocumentModel) -> list[DocumentItemModel]:
    """Kolejnosc pozycji w tabeli weryfikacji = fizyczny uklad kartki (ta sama funkcja co przy
    generowaniu TXT, patrz generator/core.py) - zeby ekran podgladu dalo sie porownac ze skanem
    "linia po linii", zamiast pokazywac przypadkowa kolejnosc zapisu w bazie (domyslne sortowanie
    relacji Document.items to `order_by=DocumentItemModel.id`, ktory jest losowym UUID)."""
    return sorted(
        document.items,
        key=lambda it: physical_order_for(it.rozpoznana_nazwa, 10000),
    )


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
        items=[_item_to_schema(it) for it in _items_in_physical_order(document)],
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


@router.patch("/{document_id}/items/{item_id}", response_model=DocumentItemOut)
def update_document_item(
    document_id: str,
    item_id: str,
    body: DocumentItemUpdateIn,
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Recznie zweryfikowana ilosc_finalna (i opcjonalnie poprawiony kod) przed generowaniem -
    patrz docs/RAPORT_ETAP_9.md. Pole nieobecne w body zostaje bez zmian (`exclude_unset`),
    `null` jawnie kasuje wartosc (np. wyklucza pozycje z generowania)."""
    document = repository.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Dokument {document_id!r} nie istnieje")
    _check_owner_or_admin(document, user)

    item = repository.get_item(session, document_id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Pozycja {item_id!r} nie istnieje")

    fields = body.model_dump(exclude_unset=True)
    update_kwargs: dict = {}
    if "ilosc_finalna" in fields:
        update_kwargs["ilosc_finalna"] = fields["ilosc_finalna"]
    if "match_kod" in fields:
        kod = fields["match_kod"]
        if kod:
            catalog = Catalog.from_db(session)
            cand = catalog.find_by_kod(kod)
            if cand is None:
                raise HTTPException(status_code=400, detail=f"Nieznany kod Optima: {kod!r}")
            product_row = session.query(ProductModel.id).filter(ProductModel.kod == cand.kod).first()
            update_kwargs.update(
                match_kod=cand.kod, match_nazwa=cand.nazwa, match_jm=cand.jm,
                matched_product_id=product_row[0] if product_row else None,
            )
        else:
            update_kwargs.update(match_kod=None, match_nazwa=None, match_jm=None, matched_product_id=None)

    item = repository.update_item(session, item, **update_kwargs)
    return _item_to_schema(item)


@router.post("/{document_id}/generate")
def generate_document_output(
    document_id: str,
    body: GenerateRequest,
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Eksport do formatu Optima (TXT, CP1250) - port generateOutput()/downloadOutput() z
    monolitu. Wymaga zakonczonego OCR (status "done") - dziala na `ilosc_finalna` pozycji
    (weryfikacja/edycja przez PATCH /{document_id}/items/{item_id})."""
    document = repository.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Dokument {document_id!r} nie istnieje")
    _check_owner_or_admin(document, user)
    if document.status != "done":
        raise HTTPException(status_code=409, detail=f"Dokument ma status {document.status!r}, oczekiwano 'done'")

    items = [
        GeneratorItem(name=it.rozpoznana_nazwa, qty=it.ilosc_finalna, off_form=it.off_form)
        for it in document.items
        if it.ilosc_finalna is not None and it.ilosc_finalna > 0
    ]

    catalog = Catalog.from_db(session)
    special_rules = rules_from_db(session)
    result = generate_output(
        items, catalog, document.magazyn, special_rules=special_rules,
        qty_mode=body.qty_mode, first_wydawka=body.first_wydawka,
    )

    text = "\n".join(result.lines)
    filename = get_filename(document.numer_projektu)
    # Nazwa pliku (z numer_projektu) moze zawierac polskie znaki - naglowek HTTP musi byc
    # ASCII, wiec dajemy zarowno fallback ASCII jak i poprawny filename* (RFC 5987).
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii")
    disposition = f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=encode_cp1250(text),
        media_type="text/plain; charset=windows-1250",
        headers={"Content-Disposition": disposition},
    )
