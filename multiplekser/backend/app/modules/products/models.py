"""Modele SQLAlchemy katalogu produktow (Etap 2) - wg ERD w docs/ETAP_0_analiza_architektury.md."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.db_types import PortableJSON


class ProductModel(Base):
    __tablename__ = "product"
    __table_args__ = (
        # Kod jest unikalny WEWNATRZ dzialu, nie globalnie (Krok Hydraulika-1) - dwa
        # niezaleznie budowane katalogi moga miec ten sam kod (np. oba maja "GRZEJNIK 1000W").
        UniqueConstraint("kod", "dzial", name="uq_product_kod_dzial"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kod: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String, nullable=False)
    jm: Mapped[str] = mapped_column(String, nullable=False, default="SZT")
    grupa: Mapped[str] = mapped_column(String, nullable=False, default="")
    dzial: Mapped[str] = mapped_column(String, nullable=False, default="elektryka", index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="generyczny")
    atrybuty: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    kolor_domniemany: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    aliasy: Mapped[list["ProductAliasModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    warianty_magazynowe: Mapped[list["WarehouseVariantModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductAliasModel(Base):
    __tablename__ = "product_alias"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False, index=True)
    alias_text: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["ProductModel"] = relationship(back_populates="aliasy")


class WarehouseVariantModel(Base):
    __tablename__ = "warehouse_variant"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False, index=True)
    magazyn: Mapped[str] = mapped_column(String, nullable=False)
    kod_docelowy: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["ProductModel"] = relationship(back_populates="warianty_magazynowe")
