"""Schematy Pydantic dla auth/uzytkownikow (Etap 5)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    email: str
    rola: str
    magazyny_dostepne: list[str] = Field(default_factory=list)
    active: bool


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessToken(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
