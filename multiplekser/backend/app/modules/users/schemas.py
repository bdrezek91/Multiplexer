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


class UserCreate(BaseModel):
    email: str
    password: str = Field(min_length=8)
    rola: str = "elektryk"
    magazyny_dostepne: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    email: str
    rola: str
    magazyny_dostepne: list[str] = Field(default_factory=list)
    active: bool


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8)
