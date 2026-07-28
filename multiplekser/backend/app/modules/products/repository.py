"""Repozytorium CRUD dla ProductModel (Etap 4) - warstwa miedzy routerem a ORM.

Odrebne od Catalog/Product w catalog.py: to sa dataclassy domenowe do CZYTANIA katalogu na
potrzeby Matchera (from_json_dict/from_db), nie do zapisu. Tu operujemy wprost na ORM.
"""
from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from .models import ProductAliasModel, ProductModel, WarehouseVariantModel
from .schemas import ProductCreate, ProductOut, ProductUpdate


class ProductNotFoundError(Exception):
    def __init__(self, kod: str):
        self.kod = kod
        super().__init__(f"Produkt o kodzie {kod!r} nie istnieje")


class DuplicateKodError(Exception):
    def __init__(self, kod: str):
        self.kod = kod
        super().__init__(f"Produkt o kodzie {kod!r} już istnieje")


def _query(session: Session):
    return session.query(ProductModel).options(
        selectinload(ProductModel.aliasy),
        selectinload(ProductModel.warianty_magazynowe),
    )


def _to_schema(row: ProductModel) -> ProductOut:
    return ProductOut(
        kod=row.kod,
        nazwa=row.nazwa,
        jm=row.jm,
        grupa=row.grupa,
        status=row.status,
        atrybuty=row.atrybuty or {},
        kolor_domniemany=row.kolor_domniemany,
        aliasy=[a.alias_text for a in row.aliasy],
        warianty_magazynowe={w.magazyn: w.kod_docelowy for w in row.warianty_magazynowe} or None,
    )


def list_products(
    session: Session,
    status: str | None = None,
    grupa: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ProductOut]:
    query = _query(session)
    if status:
        query = query.filter(ProductModel.status == status)
    if grupa:
        query = query.filter(ProductModel.grupa == grupa)
    if search:
        query = query.filter(ProductModel.nazwa.ilike(f"%{search}%"))
    rows = query.order_by(ProductModel.kod).offset(offset).limit(limit).all()
    return [_to_schema(r) for r in rows]


def get_product(session: Session, kod: str) -> ProductOut:
    row = _query(session).filter(ProductModel.kod == kod).first()
    if row is None:
        raise ProductNotFoundError(kod)
    return _to_schema(row)


def create_product(session: Session, data: ProductCreate) -> ProductOut:
    if session.query(ProductModel).filter(ProductModel.kod == data.kod).first() is not None:
        raise DuplicateKodError(data.kod)

    row = ProductModel(
        kod=data.kod, nazwa=data.nazwa, jm=data.jm, grupa=data.grupa, status=data.status,
        atrybuty=data.atrybuty, kolor_domniemany=data.kolor_domniemany,
    )
    row.aliasy = [ProductAliasModel(alias_text=a) for a in data.aliasy]
    row.warianty_magazynowe = [
        WarehouseVariantModel(magazyn=m, kod_docelowy=k) for m, k in (data.warianty_magazynowe or {}).items()
    ]
    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_schema(row)


def update_product(session: Session, kod: str, data: ProductUpdate) -> ProductOut:
    row = _query(session).filter(ProductModel.kod == kod).first()
    if row is None:
        raise ProductNotFoundError(kod)

    row.nazwa = data.nazwa
    row.jm = data.jm
    row.grupa = data.grupa
    row.status = data.status
    row.atrybuty = data.atrybuty
    row.kolor_domniemany = data.kolor_domniemany
    row.aliasy.clear()
    row.aliasy.extend(ProductAliasModel(alias_text=a) for a in data.aliasy)
    row.warianty_magazynowe.clear()
    row.warianty_magazynowe.extend(
        WarehouseVariantModel(magazyn=m, kod_docelowy=k) for m, k in (data.warianty_magazynowe or {}).items()
    )
    session.commit()
    session.refresh(row)
    return _to_schema(row)


def delete_product(session: Session, kod: str) -> None:
    row = session.query(ProductModel).filter(ProductModel.kod == kod).first()
    if row is None:
        raise ProductNotFoundError(kod)
    session.delete(row)
    session.commit()
