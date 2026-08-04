"""Model SQLAlchemy uzytkownika (Etap 5) - wg ERD z Etapu 0, z odstepstwami udokumentowanymi
w docs/RAPORT_ETAP_5.md (magazyny_dostepne jako list[str], nie uuid[] - w calym projekcie magazyn
to string, patrz WarehouseVariantModel.magazyn - nie istnieje osobna encja Warehouse).

Nazwa tabeli "app_user" (nie "user") - "user" jest zarezerwowanym slowem w Postgresie/SQL.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserModel(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    rola: Mapped[str] = mapped_column(String, nullable=False, default="magazynier")
    magazyny_dostepne: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
