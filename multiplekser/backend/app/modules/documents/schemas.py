"""Schematy Pydantic dla API dokumentow (Etap 7)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
    ilosc_finalna: float | None = None
    match_kod: str | None = None


class GenerateRequest(BaseModel):
    qty_mode: str = "real"  # "real" | "ones"
    first_wydawka: bool = False
