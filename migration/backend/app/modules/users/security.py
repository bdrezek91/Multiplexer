"""Hashowanie hasel (bcrypt) i tokeny JWT (Etap 5).

UWAGA: bcrypt jest przypiety w requirements.txt na 4.0.1 (nie najnowszy) - passlib 1.7.4
(nierozwijany od 2020) wykrywa wersje bcrypt przez atrybut usuniety w bcrypt>=4.1, co psuje
hashowanie. Znany, udokumentowany problem kompatybilnosci passlib+bcrypt - stad pin w wersji.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(password, hashed_password)


def _create_token(user_id: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: TokenType) -> str:
    """Zwraca user_id ('sub') jesli token jest wazny i wlasciwego typu, inaczej rzuca InvalidTokenError.

    Rola NIE jest odczytywana z tokenu - kazde wywolanie idzie do bazy po swiezy rekord uzytkownika
    (get_current_user), zeby zmiana roli/dezaktywacja konta dzialaly natychmiast, bez czekania na
    wygasniecie starego tokenu.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Oczekiwano tokenu typu {expected_type!r}, otrzymano {payload.get('type')!r}")
    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError("Token nie zawiera 'sub'")
    return sub
