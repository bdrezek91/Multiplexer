"""API produktow (Etap 4, chronione od Etapu 5) - pelny CRUD, sesja DB per-request.

Odczyt (GET) wymaga dowolnego zalogowanego uzytkownika, zapis (POST/PUT/DELETE) wymaga roli admin
- katalog produktowy jest wspolny dla wszystkich, ale jego edycja jest operacja administracyjna.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.users import get_current_user, require_admin

from . import knowledge, repository
from .models import ProductModel
from .schemas import AliasSuggestionOut, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])

Dzial = Literal["elektryka", "hydraulika"]


def _suggestion_to_schema(session: Session, row) -> AliasSuggestionOut:
    target = session.query(ProductModel.nazwa).filter(
        ProductModel.dzial == row.dzial,
        ProductModel.kod == row.target_kod,
    ).first()
    return AliasSuggestionOut(
        id=str(row.id),
        dzial=row.dzial,
        target_kod=row.target_kod,
        target_nazwa=target[0] if target else None,
        alias_text=row.alias_text,
        status=row.status,
        source_document_id=str(row.source_document_id) if row.source_document_id else None,
        source_item_id=str(row.source_item_id) if row.source_item_id else None,
        created_by_id=str(row.created_by_id) if row.created_by_id else None,
        resolved_by_id=str(row.resolved_by_id) if row.resolved_by_id else None,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
    )


@router.get("", response_model=list[ProductOut], dependencies=[Depends(get_current_user)])
def list_products(
    status: str | None = None,
    grupa: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=200, gt=0),
    offset: int = Query(default=0, ge=0),
    dzial: Dzial = "elektryka",
    session: Session = Depends(get_db),
):
    return repository.list_products(
        session, status=status, grupa=grupa, search=search, limit=limit, offset=offset, dzial=dzial,
    )


@router.get(
    "/knowledge/suggestions",
    response_model=list[AliasSuggestionOut],
)
def list_alias_suggestions(
    status: str = Query(default="pending", pattern="^(pending|approved|rejected)$"),
    dzial: Dzial | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    rows = knowledge.list_suggestions(session, status=status, dzial=dzial, limit=limit)
    return [_suggestion_to_schema(session, row) for row in rows]


@router.post(
    "/knowledge/suggestions/{suggestion_id}/approve",
    response_model=AliasSuggestionOut,
)
def approve_alias_suggestion(
    suggestion_id: str,
    session: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    try:
        row = knowledge.resolve_suggestion(
            session,
            suggestion_id,
            approve=True,
            resolved_by_id=admin.id,
        )
    except knowledge.AliasSuggestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Propozycja aliasu nie istnieje") from exc
    except knowledge.AliasSuggestionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _suggestion_to_schema(session, row)


@router.post(
    "/knowledge/suggestions/{suggestion_id}/reject",
    response_model=AliasSuggestionOut,
)
def reject_alias_suggestion(
    suggestion_id: str,
    session: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    try:
        row = knowledge.resolve_suggestion(
            session,
            suggestion_id,
            approve=False,
            resolved_by_id=admin.id,
        )
    except knowledge.AliasSuggestionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Propozycja aliasu nie istnieje") from exc
    return _suggestion_to_schema(session, row)


@router.get("/{kod}", response_model=ProductOut, dependencies=[Depends(get_current_user)])
def get_product(kod: str, dzial: Dzial = "elektryka", session: Session = Depends(get_db)):
    try:
        return repository.get_product(session, kod, dzial=dzial)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(require_admin)])
def create_product(data: ProductCreate, dzial: Dzial = "elektryka", session: Session = Depends(get_db)):
    try:
        return repository.create_product(session, data, dzial=dzial)
    except repository.DuplicateKodError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{kod}", response_model=ProductOut, dependencies=[Depends(require_admin)])
def update_product(kod: str, data: ProductUpdate, dzial: Dzial = "elektryka", session: Session = Depends(get_db)):
    try:
        return repository.update_product(session, kod, data, dzial=dzial)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{kod}", status_code=204, dependencies=[Depends(require_admin)])
def delete_product(kod: str, dzial: Dzial = "elektryka", session: Session = Depends(get_db)):
    try:
        repository.delete_product(session, kod, dzial=dzial)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
