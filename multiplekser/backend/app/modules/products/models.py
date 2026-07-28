"""Modele SQLAlchemy katalogu produktow (Etap 2) - wg ERD w docs/ETAP_0_analiza_architektury.md."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProductModel(Base):
    __tablename__ = "product"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kod: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    nazwa: Mapped[str] = mapped_column(String, nullable=False)
    jm: Mapped[str] = mapped_column(String, nullable=False, default="SZT")
    grupa: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="generyczny")
    atrybuty: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    kolor_domniemany: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    aliasy: Mapped[list["ProductAliasModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    warianty_magazynowe: Mapped[list["WarehouseVariantModel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductAliasModel(Base):
    __tablename__ = "product_alias"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False, index=True)
    alias_text: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["ProductModel"] = relationship(back_populates="aliasy")


class WarehouseVariantModel(Base):
    __tablename__ = "warehouse_variant"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product.id"), nullable=False, index=True)
    magazyn: Mapped[str] = mapped_column(String, nullable=False)
    kod_docelowy: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["ProductModel"] = relationship(back_populates="warianty_magazynowe")
