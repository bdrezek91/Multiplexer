"""Schematy Pydantic dla API produktow (Etap 4)."""
from __future__ import annotations

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
