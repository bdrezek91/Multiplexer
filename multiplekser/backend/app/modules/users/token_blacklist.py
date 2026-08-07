"""Rewokacja refresh tokenow (POST /auth/logout) - twardnienie bezpieczenstwa, patrz "Co
zostalo swiadomie odlozone" w docs/RAPORT_ETAP_5.md - "Brak rewokacji refresh tokenow, endpoint
/auth/logout: skradziony/przechwycony refresh token dzialal do naturalnego wygasniecia (7 dni),
bez mozliwosci uniewaznienia wczesniej".

Redis, ta sama instancja co rate limiter/cooldown OCR/blokada logowania (lockout.py). Wpis 'jti'
na liscie zyje dokladnie tyle, ile token i tak bylby wazny (dluzej nie ma sensu - token wygasnie
sam), stad TTL przekazywany z zewnatrz (security.RefreshTokenData.expires_in_seconds), nie
staly jak w innych modulach Redis tego projektu.

Tylko refresh tokeny sa tu sprawdzane - access token ma krotki czas zycia (domyslnie 30 min,
patrz settings.access_token_expire_minutes), wiec po wylogowaniu pozostaje uzywalny co najwyzej
tyle - zaakceptowany kompromis (rewokacja access tokenow wymagalaby odpytywania Redis przy
KAZDYM zadaniu API chronionym przez get_current_user, nie tylko przy odswiezaniu)."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "multiplekser:auth:revoked-refresh"


class TokenBlacklistStore(Protocol):
    def revoke(self, jti: str, ttl_seconds: int) -> None: ...
    def is_revoked(self, jti: str) -> bool: ...


class RedisTokenBlacklistStore:
    def __init__(self, client: Redis):
        self.client = client

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            self.client.set(f"{_KEY_PREFIX}:{jti}", "1", ex=ttl_seconds)
        except (RedisError, OSError):
            logger.warning("Auth blacklist - nie udalo sie zapisac rewokacji w Redis", exc_info=True)

    def is_revoked(self, jti: str) -> bool:
        try:
            return bool(self.client.exists(f"{_KEY_PREFIX}:{jti}"))
        except (RedisError, OSError):
            # Fail-open, tak jak lockout.py/cooldown.py - Redis niedostepny juz i tak psuje
            # rate limiter/Celery w tym stosie, wiec spojne zachowanie zamiast twardej blokady
            # logowania calego systemu przy chwilowej awarii Redis.
            logger.warning("Auth blacklist - Redis niedostepny, przepuszczam refresh token", exc_info=True)
            return False


@lru_cache(maxsize=1)
def get_token_blacklist_store() -> RedisTokenBlacklistStore:
    return RedisTokenBlacklistStore(Redis.from_url(settings.redis_url, decode_responses=True))
