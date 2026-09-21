"""Schematy Pydantic dla API dokumentow (Etap 7)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DocumentItemOut(BaseModel):
    id: str
    rozpoznana_nazwa: str
    ilosc_wydana: float | None
    ilosc_zuzyta: float | None
    ilosc_finalna: float | None
    match_kod: str | None
    match_nazwa: str | None
    match_jm: str | None
    match_quality: str
    match_score: float
    off_form: bool
    needs_review: bool
    form_note: str
    uwagi: str
    confidence: float | None
    ilosc_z_dodatkowej_kontroli: bool


class AITraceEventOut(BaseModel):
    status: str
    stage: str | None = None
    provider: str | None = None
    model: str | None = None
    label: str | None = None
    reason: str | None = None
    step: int | None = None
    total_steps: int | None = None
    duration_ms: int | None = None
    attempt: int | None = None
    target: str | None = None
    created_at: datetime


class DocumentOut(BaseModel):
    id: str
    status: str
    numer_projektu: str | None
    pracownik: str | None = None
    numer_plomby: str | None = None
    source_type: str
    magazyn: str | None
    dzial: str | None
    dzial_confidence: float | None
    original_filename: str
    used_provider: str | None
    rejected_count: int
    error_message: str | None
    ai_trace: list[AITraceEventOut] = Field(default_factory=list)
    created_at: datetime
    items: list[DocumentItemOut]
    # Czy dokument ma aktywny link Optima (2026-09-17) - NIGDY sam token/URL (ten wraca
    # wylacznie raz, z POST /{id}/optima-link) - patrz uzasadnienie w repository.py.
    optima_link_active: bool = False


class DocumentCreatedOut(BaseModel):
    id: str
    status: str


class DocumentItemUpdateIn(BaseModel):
    """Recznie zweryfikowana ilosc (i opcjonalnie poprawiony kod) przed generowaniem - patrz
    docs/RAPORT_ETAP_9.md, "Ilosc finalna". Pola nieustawione (None w requescie) NIE sa
    nadpisywane innymi polami - ilosc_finalna=null jawnie kasuje ilosc (wyklucza pozycje z
    generowania), ale brak pola w JSON w ogole zostawia je bez zmian (patrz `exclude_unset`)."""
    ilosc_finalna: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    match_kod: str | None = None


class DocumentItemAddIn(BaseModel):
    """Reczne dodanie pozycji spoza OCR (np. cos pominietego na papierowej wydawce) - patrz
    historia czatu. W przeciwienstwie do PATCH .../items/{id} (poprawka JUZ istniejacej pozycji),
    to tworzy NOWA pozycje, od razu z potwierdzonym dopasowaniem - uzytkownik wybiera produkt
    wprost z katalogu (tego samego dzialu co dokument), wiec nie ma tu niejednoznacznosci do
    rozstrzygniecia jak przy OCR."""
    match_kod: str
    ilosc_finalna: float = Field(gt=0, allow_inf_nan=False)


class GenerateRequest(BaseModel):
    qty_mode: str = "real"  # "real" | "ones"
    first_wydawka: bool = False


class MagazynUpdateIn(BaseModel):
    """Zmiana magazynu PO zakonczonym OCR (np. gdy nie wybrano go przy uploadzie) - Krok
    Hydraulika-6. `null` kasuje magazyn (dokument bez magazynu)."""
    magazyn: str | None = None


class MetadaneUpdateIn(BaseModel):
    """Reczna korekta pol odczytanych przez OCR z naglowka formularza (2026-09-17, rozszerzone
    2026-09-18 o numer_projektu) - pracownik, numer plomby-rozdzielni i numer projektu bywaja
    odczytane bledne/niepewne, tak samo jak reszta OCR. Pole nieobecne w body (`exclude_unset`)
    zostaje bez zmian, jawne `null` kasuje wartosc."""
    pracownik: str | None = None
    numer_plomby: str | None = None
    numer_projektu: str | None = None


class DocumentReportCreateIn(BaseModel):
    """Zgloszenie problemu na dokumencie (2026-09-08) - wolny tekst opisujacy co jest zle na
    tym konkretnym skanie (np. zle dopasowanie, zla ilosc)."""
    opis: str = Field(min_length=1, max_length=4000)


class OptimaLinkOut(BaseModel):
    """Odpowiedz POST /{document_id}/optima-link - jedyny moment, w ktorym pelny URL (z surowym
    tokenem) jest widoczny. Ani baza, ani zaden inny endpoint go pozniej nie zwraca - patrz
    DocumentOut.optima_link_active (tylko flaga, bez tokena)."""
    url: str


class DocumentReportOut(BaseModel):
    id: str
    document_id: str
    document_original_filename: str
    reported_by_email: str
    opis: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class UserDocumentStatsOut(BaseModel):
    """Jeden wiersz zestawienia oszczednosci (2026-09-21) - patrz
    repository.get_document_stats_per_user."""
    user_id: str
    email: str
    dokumenty: int
    minuty_zaoszczedzone: int
    pieniadze_zaoszczedzone: float


class DocumentStatsOut(BaseModel):
    """Zestawienie dla panelu administratora: ile dokumentow przerobil kazdy uzytkownik i ile to
    daje zaoszczedzonego czasu/pieniedzy wzgledem recznego wprowadzania - zalozenia (8 min/wydawke,
    55 zl brutto/h kosztu pracodawcy) patrz repository.py."""
    per_user: list[UserDocumentStatsOut]
    razem_dokumenty: int
    razem_minuty_zaoszczedzone: int
    razem_pieniadze_zaoszczedzone: float
    minuty_na_dokument: int
    stawka_pln_za_h: float
