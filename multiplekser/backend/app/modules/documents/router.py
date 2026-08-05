"""Endpoint dokumentow (Etap 7) - ASYNCHRONICZNY nastepca /ocr/recognize z Etapu 6 (usuniety -
byl swiadomie oznaczony jako ryzyko: blokowal request HTTP do 90s, zamiast kolejki w tle).

POST /documents zapisuje plik do storage, tworzy rekord Document (status "queued") i zleca
przetwarzanie Celery - odpowiada natychmiast (202). GET /documents/{id} pozwala odpytac status
i (po zakonczeniu) wynik. Wlasciciel dokumentu lub admin - inni dostaja 403 (patrz test RBAC).
"""
from __future__ import annotations

import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.generator import (
    GeneratorItem,
    encode_cp1250,
    generate_output,
    generate_output_hydraulika,
    get_filename,
    physical_order_for,
)
from app.modules.matcher import (
    QUALITY_BAD,
    QUALITY_OK,
    match_against_catalog,
    match_against_catalog_hydraulika,
    rules_from_db,
)
from app.modules.products import Catalog
from app.modules.products.models import ProductModel
from app.modules.users import get_current_user
from app.modules.users.deps import check_magazyn_access
from app.modules.users.models import UserModel

from . import repository
from .models import DocumentItemModel, DocumentModel
from .schemas import (
    DocumentCreatedOut,
    DocumentItemOut,
    DocumentItemAddIn,
    DocumentItemUpdateIn,
    DocumentOut,
    GenerateRequest,
    MagazynUpdateIn,
)
from .storage import get_storage
from .tasks import dispatch_ocr_task

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"


def _build_file_key(document_id: uuid.UUID, page_number: int, original_filename: str) -> str:
    # Przegladarka zwykle wysyla sama nazwe, ale usuwamy tez ewentualna sciezke klienta.
    safe_filename = original_filename.replace("\\", "/").rsplit("/", 1)[-1] or "plik"
    return f"documents/{document_id}/{page_number:03d}-{uuid.uuid4().hex}-{safe_filename}"


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
    """Kolejnosc pozycji w tabeli weryfikacji. Elektryka: fizyczny uklad kartki (ta sama funkcja
    co przy generowaniu TXT, patrz generator/core.py) - zeby ekran podgladu dalo sie porownac ze
    skanem "linia po linii". Hydraulika NIE ma takiego ukladu w zrodle (patrz generator/
    core_hydraulika.py) - `document.items` jest juz w kolejnosci odczytu OCR dzieki
    `DocumentItemModel.sequence` (relacja `Document.items` sortuje po niej), wystarczy zwrocic
    bez zmian."""
    if document.dzial and document.dzial != "elektryka":
        return document.items
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
        dzial=document.dzial,
        dzial_confidence=document.dzial_confidence,
        original_filename=document.original_filename,
        used_provider=document.used_provider,
        rejected_count=document.rejected_count,
        error_message=document.error_message,
        created_at=document.created_at,
        items=[_item_to_schema(it) for it in _items_in_physical_order(document)],
    )


def _check_owner_or_admin(document: DocumentModel, user: UserModel) -> None:
    if user.rola != "admin" and document.user_id != user.id:
        raise HTTPException(status_code=403, detail="Brak dostępu do tego dokumentu")


@router.post("", response_model=DocumentCreatedOut, status_code=202)
async def create_document(
    plik: list[UploadFile] = File(...),
    magazyn: str | None = Form(default=None),
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """`plik` przyjmuje jeden lub wiecej plikow - wiecej niz jeden gdy papierowa wydawka nie
    zmiescila sie na jednym zdjeciu z telefonu (w przeciwienstwie do skanu PDF, ktory moze miec
    kilka stron w jednym pliku) - patrz historia czatu. Wszystkie pliki trafiaja do OCR jako
    kolejne strony JEDNEGO dokumentu (patrz tasks.py/ocr/providers.py), nie jako osobne
    dokumenty."""
    check_magazyn_access(user, magazyn)

    if not plik:
        raise HTTPException(status_code=400, detail="Brak pliku")

    document_id = uuid.uuid4()
    prepared: list[tuple[str, bytes, str, str]] = []  # (file_key, raw, mime, original_filename)
    for page_number, upload in enumerate(plik, start=1):
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Pusty plik")
        is_pdf = upload.content_type == _PDF_MIME or (upload.filename or "").lower().endswith(".pdf")
        mime = _PDF_MIME if is_pdf else (upload.content_type or "application/octet-stream")
        original_filename = upload.filename or "plik"
        # Nazwa pliku nie jest unikalna (telefon/skaner czesto nadaje kazdej stronie np.
        # "skan.jpg"). UUID zapobiega nadpisaniu poprzedniej strony, a numer zachowuje
        # czytelna kolejnosc obiektow w storage.
        file_key = _build_file_key(document_id, page_number, original_filename)
        prepared.append((file_key, raw, mime, original_filename))

    storage = get_storage()
    uploaded_keys: list[str] = []
    document: DocumentModel | None = None
    try:
        for file_key, raw, mime, _original_filename in prepared:
            storage.upload(file_key, raw, mime)
            uploaded_keys.append(file_key)

        first_key, _first_raw, first_mime, first_name = prepared[0]
        document = repository.create_document(
            session, document_id=document_id, user_id=user.id, file_key=first_key, mime=first_mime,
            original_filename=first_name, magazyn=magazyn,
            extra_files=[
                (file_key, mime)
                for file_key, _raw, mime, _original_filename in prepared[1:]
            ],
        )

        dispatch_ocr_task(str(document.id))
    except Exception:
        session.rollback()
        if document is not None:
            try:
                session.delete(document)
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Nie udalo sie usunac rekordu dokumentu %s po bledzie uploadu", document_id)
        for file_key in reversed(uploaded_keys):
            try:
                storage.delete(file_key)
            except Exception:
                logger.exception("Nie udalo sie usunac osieroconego pliku %s", file_key)
        raise

    assert document is not None
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
            catalog = Catalog.from_db(session, dzial=document.dzial or "elektryka")
            cand = catalog.find_by_kod(kod)
            if cand is None:
                raise HTTPException(status_code=400, detail=f"Nieznany kod Optima: {kod!r}")
            product_row = session.query(ProductModel.id).filter(
                ProductModel.kod == cand.kod, ProductModel.dzial == (document.dzial or "elektryka"),
            ).first()
            update_kwargs.update(
                match_kod=cand.kod, match_nazwa=cand.nazwa, match_jm=cand.jm,
                matched_product_id=product_row[0] if product_row else None,
                # Reczna korekta = potwierdzone dopasowanie: przelacza badge z "Brak dopasowania"
                # na "OK" i sprawia, ze generator (core_elektryka.py/core_hydraulika.py) uzyje
                # tego kodu wprost zamiast ponownie dopasowywac od zera surowa nazwe z OCR.
                match_quality=QUALITY_OK, match_score=1.0,
            )
        else:
            update_kwargs.update(
                match_kod=None, match_nazwa=None, match_jm=None, matched_product_id=None,
                match_quality=QUALITY_BAD, match_score=0.0,
            )

    item = repository.update_item(session, item, **update_kwargs)
    return _item_to_schema(item)


@router.post("/{document_id}/items", response_model=DocumentItemOut, status_code=201)
def add_document_item(
    document_id: str,
    body: DocumentItemAddIn,
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Reczne dodanie pozycji spoza OCR (np. cos pominietego na papierowej wydawce) - patrz
    historia czatu. Kod musi istniec w katalogu WLASCIWEGO dzialu dokumentu (tak samo jak
    walidacja w update_document_item). Nowa pozycja trafia do generowania od razu z quality
    "ok"."""
    document = repository.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Dokument {document_id!r} nie istnieje")
    _check_owner_or_admin(document, user)
    if document.status != "done":
        raise HTTPException(status_code=409, detail=f"Dokument ma status {document.status!r}, oczekiwano 'done'")

    dzial = document.dzial or "elektryka"
    catalog = Catalog.from_db(session, dzial=dzial)
    cand = catalog.find_by_kod(body.match_kod)
    if cand is None:
        raise HTTPException(status_code=400, detail=f"Nieznany kod Optima: {body.match_kod!r}")
    product_row = session.query(ProductModel.id).filter(
        ProductModel.kod == cand.kod, ProductModel.dzial == dzial,
    ).first()

    item = repository.add_manual_item(
        session, document,
        rozpoznana_nazwa=cand.nazwa, match_kod=cand.kod, match_nazwa=cand.nazwa, match_jm=cand.jm,
        matched_product_id=product_row[0] if product_row else None, ilosc_finalna=body.ilosc_finalna,
    )
    return _item_to_schema(item)


@router.patch("/{document_id}/magazyn", response_model=DocumentOut)
def update_document_magazyn(
    document_id: str,
    body: MagazynUpdateIn,
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    """Zmiana magazynu PO zakonczonym OCR (Krok Hydraulika-6) - np. gdy nie wybrano go przy
    uploadzie. Ponownie dopasowuje WSZYSTKIE pozycje z nowym magazynem (R5: podstawienie kodu
    wg wariantu magazynowego zalezy od magazynu), nie tylko podmienia etykiete - inaczej
    wygenerowany plik mialby kod dopasowany do STAREGO magazynu.

    UWAGA: to nadpisuje ewentualne reczne korekty `match_kod` zrobione wczesniej przez
    PATCH .../items/{item_id} na tym dokumencie (ten endpoint nie wie, ktore dopasowania byly
    poprawiane recznie) - akceptowany kompromis, opisany w docs/RAPORT_ETAP_HYDRAULIKA_6.md."""
    document = repository.get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Dokument {document_id!r} nie istnieje")
    _check_owner_or_admin(document, user)
    check_magazyn_access(user, body.magazyn)

    dzial = document.dzial or "elektryka"
    catalog = Catalog.from_db(session, dzial=dzial)
    repository.set_magazyn(session, document, body.magazyn)

    special_rules = None if dzial == "hydraulika" else rules_from_db(session)
    for item in document.items:
        if dzial == "hydraulika":
            match = match_against_catalog_hydraulika(item.rozpoznana_nazwa, catalog, magazyn=body.magazyn)
        else:
            match = match_against_catalog(
                item.rozpoznana_nazwa, catalog, magazyn=body.magazyn, special_rules=special_rules,
            )
        product_row = None
        if match.kod:
            product_row = session.query(ProductModel.id).filter(
                ProductModel.kod == match.kod, ProductModel.dzial == dzial,
            ).first()
        repository.update_item(
            session, item,
            match_kod=match.kod, match_nazwa=match.nazwa, match_jm=match.jm_override,
            match_quality=match.quality, match_score=match.ratio,
            matched_product_id=product_row[0] if product_row else None,
            commit=False,
        )
    session.commit()
    session.refresh(document)
    return _to_schema(document)


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

    dzial = document.dzial or "elektryka"
    items = [
        GeneratorItem(
            name=it.rozpoznana_nazwa, qty=it.ilosc_finalna, off_form=it.off_form,
            match_kod=it.match_kod, match_nazwa=it.match_nazwa, match_jm=it.match_jm,
            match_quality=it.match_quality, match_score=it.match_score,
        )
        for it in _items_in_physical_order(document)
        if it.ilosc_finalna is not None and it.ilosc_finalna > 0
    ]

    catalog = Catalog.from_db(session, dzial=dzial)
    if dzial == "hydraulika":
        result = generate_output_hydraulika(items, catalog, document.magazyn, qty_mode=body.qty_mode)
    else:
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
