"""Model SQLAlchemy uzytkownika (Etap 5) - wg ERD z Etapu 0, z odstepstwami udokumentowanymi
w docs/RAPORT_ETAP_5.md (magazyny_dostepne jako list[str], nie uuid[] - w calym projekcie magazyn
to string, patrz WarehouseVariantModel.magazyn - nie istnieje osobna encja Warehouse).

Nazwa tabeli "app_user" (nie "user") - "user" jest zarezerwowanym slowem w Postgresie/SQL.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, String, Uuid
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
    # Trwaly, narastajacy licznik ukonczonych dokumentow (statystyki wydajnosci, Users/UsersPage) -
    # NIE wolno liczyc tego z live COUNT(DocumentModel WHERE status="done"), bo retention.py
    # kasuje stare dokumenty (zachowuje tylko document_retention_limit najnowszych) - taki live
    # COUNT po prostu spada w miare jak retencja usuwa stare wpisy, mimo ze uzytkownik naprawde
    # przerobil wiecej dokumentow niz akurat zostalo w bazie (bug wykryty 2026-09-29, realny
    # spadek pokazywanych oszczednosci z >1300 zl do 132 zl). Inkrementowany raz, w momencie
    # oznaczenia dokumentu jako "done" (documents/repository.py: mark_done()), nigdy nie
    # dekrementowany przez retencje.
    dokumenty_ukonczone_licznik: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
