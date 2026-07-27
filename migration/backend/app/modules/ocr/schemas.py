"""Schematy Pydantic dla API OCR (Etap 6)."""
from __future__ import annotations

from pydantic import BaseModel


class OCRMatchOut(BaseModel):
    kod: str | None
    nazwa: str | None
    quality: str
    ratio: float
    jm: str | None


class OCRItemOut(BaseModel):
    rozpoznana_nazwa: str
    ilosc_wydana: str | None
    ilosc_zuzyta: str | None
    uwagi: str
    confidence: float | None
    needs_review: bool
    off_form: bool
    form_note: str
    match: OCRMatchOut


class OCRResultOut(BaseModel):
    numer_projektu: str | None
    pozycje: list[OCRItemOut]
    used_provider: str
    rejected_count: int
