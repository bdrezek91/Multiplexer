"""Hashowanie hasel (bcrypt) i tokeny JWT (Etap 5).

UWAGA: bcrypt jest przypiety w requirements.txt na 4.0.1 (nie najnowszy) - passlib 1.7.4
(nierozwijany od 2020) wykrywa wersje bcrypt przez atrybut usuniety w bcrypt>=4.1, co psuje
hashowanie. Znany, udokumentowany problem kompatybilnosci passlib+bcrypt - stad pin w wersji.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]

# Haslo-placeholder do wyrownania czasu odpowiedzi logowania (patrz router.py: login()) - gdy
# konto nie istnieje, weryfikujemy hasla wobec tego hasha zamiast krotko-obwodowac cala
# weryfikacje. Bez tego czas odpowiedzi 401 zdradza, czy podany e-mail istnieje w bazie (bcrypt
# ~100ms tylko dla istniejacych kont) - luka do enumeracji kont. Stala, nie generowana za kazdym
# razem hash_password() - koszt liczenia hasha ma byc poniesiony raz przy imporcie modulu, nie
# przy kazdym nieudanym logowaniu.
DUMMY_PASSWORD_HASH = "$2b$12$lWzs2SZtIn5H0P91ExkNz.mIPk6JerodhR95hOAsUZwc8qThMBzMu"


class InvalidTokenError(Exception):
    pass


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(password, hashed_password)


def _create_token(user_id: str, token_type: TokenType, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id, "type": token_type, "iat": now, "exp": now + expires_delta,
        # 'jti' - id unikalny per token, uzywany tylko dla refresh tokenow (patrz
        # decode_refresh_token/token_blacklist.py, POST /auth/logout) do wpisania na
        # blackliste rewokacji w Redis. Generowany tez dla access tokenow dla spojnosci -
        # nieuzywany, zero kosztu.
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return _create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes))


def create_refresh_token(user_id: str) -> str:
    return _create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days))


def _decode_payload(token: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Oczekiwano tokenu typu {expected_type!r}, otrzymano {payload.get('type')!r}")
    if not payload.get("sub"):
        raise InvalidTokenError("Token nie zawiera 'sub'")
    return payload


def decode_token(token: str, expected_type: TokenType) -> str:
    """Zwraca user_id ('sub') jesli token jest wazny i wlasciwego typu, inaczej rzuca InvalidTokenError.

    Rola NIE jest odczytywana z tokenu - kazde wywolanie idzie do bazy po swiezy rekord uzytkownika
    (get_current_user), zeby zmiana roli/dezaktywacja konta dzialaly natychmiast, bez czekania na
    wygasniecie starego tokenu.
    """
    return _decode_payload(token, expected_type)["sub"]


@dataclass(frozen=True)
class RefreshTokenData:
    user_id: str
    jti: str
    expires_in_seconds: int


def decode_refresh_token(token: str) -> RefreshTokenData:
    """Jak decode_token(token, "refresh"), ale zwraca tez 'jti' (id tokenu, do sprawdzenia/
    zapisania na blackliscie rewokacji - patrz token_blacklist.py, POST /auth/refresh i
    POST /auth/logout) oraz pozostaly czas zycia tokenu w sekundach (TTL wpisu na blackliscie -
    nie ma sensu trzymac go dluzej niz token i tak bylby wazny)."""
    payload = _decode_payload(token, "refresh")
    jti = payload.get("jti")
    if not jti:
        raise InvalidTokenError("Refresh token nie zawiera 'jti'")
    exp = payload.get("exp")
    expires_in = max(int(exp - datetime.now(timezone.utc).timestamp()), 0) if exp else 0
    return RefreshTokenData(user_id=payload["sub"], jti=jti, expires_in_seconds=expires_in)
