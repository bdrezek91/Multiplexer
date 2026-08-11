"""Blokada konta po serii nieudanych logowan (twardnienie bezpieczenstwa, patrz "Co zostalo
swiadomie odlozone" w docs/RAPORT_ETAP_5.md - "Rate limiting logowania / blokada po nieudanych
probach"). Rate limiting per-IP na /auth/token (app/core/rate_limit.py, Etap "quick winy")
juz istnieje, ale chroni tylko przed jednym zrodlem requestow - nie przed rozproszonym atakiem
(wiele adresow IP probujacych to samo konto). Ten modul dodaje osobna, per-konto blokade w
Redis (ta sama instancja co rate limiter/broker Celery/cooldown OCR - zero nowej infrastruktury,
patrz ocr/cooldown.py po ten sam wzorzec).

5 nieudanych prob w oknie 15 minut blokuje logowanie na danym koncie na kolejne 15 minut,
niezaleznie od adresu IP z ktorego przychodza proby. Udane logowanie zeruje licznik.
"""
from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Protocol

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_FAILED_ATTEMPTS = 5
_ATTEMPTS_WINDOW_SECONDS = 15 * 60
_LOCKOUT_SECONDS = 15 * 60
_KEY_PREFIX = "multiplekser:auth:lockout"


class LoginLockoutStore(Protocol):
    def remaining_seconds(self, email: str) -> int: ...
    def record_failure(self, email: str) -> int: ...
    def reset(self, email: str) -> None: ...


class RedisLoginLockoutStore:
    def __init__(self, client: Redis):
        self.client = client

    @staticmethod
    def _token(email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:20]

    def _keys(self, email: str) -> tuple[str, str]:
        token = self._token(email)
        return f"{_KEY_PREFIX}:{token}:locked", f"{_KEY_PREFIX}:{token}:attempts"

    def remaining_seconds(self, email: str) -> int:
        locked_key, _ = self._keys(email)
        try:
            return max(int(self.client.ttl(locked_key)), 0)
        except (RedisError, OSError, ValueError):
            logger.warning("Auth lockout - Redis niedostepny", exc_info=True)
            return 0

    def record_failure(self, email: str) -> int:
        locked_key, attempts_key = self._keys(email)
        try:
            attempts = int(self.client.incr(attempts_key))
            self.client.expire(attempts_key, _ATTEMPTS_WINDOW_SECONDS)
            if attempts >= _MAX_FAILED_ATTEMPTS:
                self.client.set(locked_key, "1", ex=_LOCKOUT_SECONDS)
                return _LOCKOUT_SECONDS
            return 0
        except (RedisError, OSError, ValueError):
            logger.warning("Auth lockout - nie udalo sie zapisac proby w Redis", exc_info=True)
            return 0

    def reset(self, email: str) -> None:
        locked_key, attempts_key = self._keys(email)
        try:
            self.client.delete(locked_key, attempts_key)
        except (RedisError, OSError):
            logger.warning("Auth lockout - nie udalo sie wyzerowac licznika w Redis", exc_info=True)


@lru_cache(maxsize=1)
def get_login_lockout_store() -> RedisLoginLockoutStore:
    # Polaczenie nawiazywane leniwie przy pierwszym uzyciu, tak jak w ocr/cooldown.py.
    return RedisLoginLockoutStore(Redis.from_url(settings.redis_url, decode_responses=True))
