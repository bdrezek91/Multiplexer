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
