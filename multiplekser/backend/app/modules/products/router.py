"""API produktow (Etap 4, chronione od Etapu 5) - pelny CRUD, sesja DB per-request.

Odczyt (GET) wymaga dowolnego zalogowanego uzytkownika, zapis (POST/PUT/DELETE) wymaga roli admin
- katalog produktowy jest wspolny dla wszystkich, ale jego edycja jest operacja administracyjna.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.users import get_current_user, require_admin

from . import repository
from .schemas import ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut], dependencies=[Depends(get_current_user)])
def list_products(
    status: str | None = None,
    grupa: str | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=200, gt=0),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
):
    return repository.list_products(session, status=status, grupa=grupa, search=search, limit=limit, offset=offset)


@router.get("/{kod}", response_model=ProductOut, dependencies=[Depends(get_current_user)])
def get_product(kod: str, session: Session = Depends(get_db)):
    try:
        return repository.get_product(session, kod)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(require_admin)])
def create_product(data: ProductCreate, session: Session = Depends(get_db)):
    try:
        return repository.create_product(session, data)
    except repository.DuplicateKodError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{kod}", response_model=ProductOut, dependencies=[Depends(require_admin)])
def update_product(kod: str, data: ProductUpdate, session: Session = Depends(get_db)):
    try:
        return repository.update_product(session, kod, data)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{kod}", status_code=204, dependencies=[Depends(require_admin)])
def delete_product(kod: str, session: Session = Depends(get_db)):
    try:
        repository.delete_product(session, kod)
    except repository.ProductNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
