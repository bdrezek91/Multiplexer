"""Modele SQLAlchemy Document/DocumentItem (Etap 7) - wg ERD z Etapu 0, z udokumentowanymi
rozszerzeniami (patrz docs/RAPORT_ETAP_7.md, "Decyzje projektowe"): `file_key`/`mime`/
`original_filename` (klucz w storage + jak przetworzyc plik), `magazyn` (parametr dopasowania
uzyty przy przetwarzaniu - audytowalnosc), `used_provider`/`rejected_count`/`error_message`
(diagnostyka), `needs_review`/`form_note`/`uwagi`/`confidence` (dane z pipeline'u OCR z Etapu 6,
ktore inaczej zostalyby po cichu odrzucone przy zapisie), `match_kod`/`match_nazwa`/`match_jm`
(zdenormalizowane obok `matched_product_id` - patrz komentarz przy polu nizej).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

# "queued" -> "processing" -> "done" | "error"
DOCUMENT_STATUSES = ("queued", "processing", "done", "error")


class DocumentModel(Base):
    __tablename__ = "document"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"), nullable=False, index=True)

    numer_projektu: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False, default="ai_scan")
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued", index=True)
    magazyn: Mapped[str | None] = mapped_column(String, nullable=True)
    # Wykryty automatycznie przez klasyfikacje OCR (Krok Hydraulika-3) - null dopoki przetwarzanie
    # nie dojdzie do etapu klasyfikacji (queued/processing przerwane bledem przed nia).
    dzial: Mapped[str | None] = mapped_column(String, nullable=True)
    dzial_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    file_key: Mapped[str] = mapped_column(String, nullable=False)
    mime: Mapped[str] = mapped_column(String, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)

    used_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    # Bezpieczny, uzytkowy dziennik decyzji lancucha AI wyswietlany na stronie dokumentu.
    # Zawiera tylko model/status/powod/czas - nigdy prompt, odpowiedz, plik ani klucz API.
    ai_trace: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    items: Mapped[list["DocumentItemModel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentItemModel.sequence",
    )
    # Strony 2+ dokumentu wieloplikowego (np. dwa osobne zdjecia z telefonu = dwie strony jednej
    # wydawki) - patrz historia czatu. Pierwsza strona zostaje w file_key/mime powyzej (wsteczna
    # zgodnosc z dokumentami sprzed tej zmiany, ktore maja dokladnie jeden plik i zero wierszy
    # tutaj). `extra_files` bo `files` kolidowaloby nazwa z `plik`/upload w API.
    extra_files: Mapped[list["DocumentFileModel"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentFileModel.sequence",
    )


class DocumentItemModel(Base):
    __tablename__ = "document_item"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    # Kolejnosc odczytu OCR (Krok Hydraulika-5) - `id` (UUID losowy) nigdy nie byl uzytecznym
    # kluczem sortowania; Elektryka i tak zawsze przesortowuje wynik przez `physical_order_for`
    # wiec problem byl niewidoczny, ale Hydraulika NIE ma takiego sortowania w zrodle (kolejnosc
    # wyniku = kolejnosc w dokumencie zrodlowym) - bez tej kolumny generator dostawalby
    # pozycje w przypadkowej kolejnosci UUID zamiast kolejnosci z OCR.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    rozpoznana_nazwa: Mapped[str] = mapped_column(String, nullable=False)
    # matched_product_id to FK (integralnosc referencyjna), ale kod/nazwa/jm dopasowania sa
    # DODATKOWO zdenormalizowane ponizej - wynik OCR to zapis historyczny "co dopasowalismy W TYM
    # MOMENCIE"; gdyby polegac wylacznie na joinie przez FK, pozniejsza edycja/usuniecie produktu
    # w katalogu cicho zmienioby tresc juz zakonczonego dokumentu.
    matched_product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product.id"), nullable=True)
    match_kod: Mapped[str | None] = mapped_column(String, nullable=True)
    match_nazwa: Mapped[str | None] = mapped_column(String, nullable=True)
    match_jm: Mapped[str | None] = mapped_column(String, nullable=True)

    ilosc_wydana: Mapped[float | None] = mapped_column(Float, nullable=True)
    ilosc_zuzyta: Mapped[float | None] = mapped_column(Float, nullable=True)
    ilosc_finalna: Mapped[float | None] = mapped_column(Float, nullable=True)

    match_quality: Mapped[str] = mapped_column(String, nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    off_form: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    form_note: Mapped[str] = mapped_column(String, nullable=False, default="")
    uwagi: Mapped[str] = mapped_column(String, nullable=False, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped["DocumentModel"] = relationship(back_populates="items")


class DocumentFileModel(Base):
    """Strona 2+ dokumentu wieloplikowego (patrz DocumentModel.extra_files) - np. dwa osobne
    zdjecia z telefonu tej samej papierowej wydawki (jedno zdjecie = jedna kartka, w
    przeciwienstwie do skanu PDF, ktory moze miec wiele stron w jednym pliku)."""
    __tablename__ = "document_file"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_key: Mapped[str] = mapped_column(String, nullable=False)
    mime: Mapped[str] = mapped_column(String, nullable=False)

    document: Mapped["DocumentModel"] = relationship(back_populates="extra_files")
