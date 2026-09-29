"""Schematy Pydantic dla API produktow (Etap 4)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProductBase(BaseModel):
    nazwa: str
    jm: str = "SZT"
    grupa: str = ""
    status: str = "generyczny"
    atrybuty: dict = Field(default_factory=dict)
    kolor_domniemany: bool = False
    aliasy: list[str] = Field(default_factory=list)
    warianty_magazynowe: dict[str, str] | None = None


class ProductCreate(ProductBase):
    kod: str


class ProductUpdate(ProductBase):
    pass


class ProductOut(ProductBase):
    kod: str
    dzial: str = "elektryka"


class AliasSuggestionOut(BaseModel):
    id: str
    dzial: str
    target_kod: str
    target_nazwa: str | None = None
    alias_text: str
    status: str
    source_document_id: str | None = None
    source_item_id: str | None = None
    created_by_id: str | None = None
    resolved_by_id: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
