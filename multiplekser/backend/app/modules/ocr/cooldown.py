"""Wspolna blokada modeli po API 429.

Redis jest juz brokerem Celery, wiec ten sam stan widza wszystkie procesy workera oraz kolejne
dokumenty. Czasy rosna przy kolejnych bledach danego kroku: 10, 15, 20 minut; nastepne pozostaja
na 20 minut. Pierwsza poprawna odpowiedz zeruje licznik.
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

_COOLDOWN_MINUTES = (10, 15, 20)
_STRIKE_TTL_SECONDS = 24 * 60 * 60
_KEY_PREFIX = "multiplekser:ocr:model-cooldown"


class OCRCooldownStore(Protocol):
    def remaining_seconds(self, step_label: str) -> int: ...
    def record_rate_limit(self, step_label: str) -> int: ...
    def reset(self, step_label: str) -> None: ...


class RedisOCRCooldownStore:
    def __init__(self, client: Redis):
        self.client = client

    @staticmethod
    def _token(step_label: str) -> str:
        return hashlib.sha256(step_label.encode("utf-8")).hexdigest()[:20]

    def _keys(self, step_label: str) -> tuple[str, str]:
        token = self._token(step_label)
        return f"{_KEY_PREFIX}:{token}:blocked", f"{_KEY_PREFIX}:{token}:strikes"

    def remaining_seconds(self, step_label: str) -> int:
        blocked_key, _ = self._keys(step_label)
        try:
            ttl = self.client.ttl(blocked_key)
            return max(int(ttl), 0)
        except (RedisError, OSError, ValueError):
            logger.warning("OCR AI - Redis cooldown niedostepny", exc_info=True)
            return 0

    def record_rate_limit(self, step_label: str) -> int:
        blocked_key, strikes_key = self._keys(step_label)
        try:
            strikes = int(self.client.incr(strikes_key))
            self.client.expire(strikes_key, _STRIKE_TTL_SECONDS)
            minutes = _COOLDOWN_MINUTES[min(strikes - 1, len(_COOLDOWN_MINUTES) - 1)]
            self.client.set(blocked_key, "1", ex=minutes * 60)
            return minutes
        except (RedisError, OSError, ValueError):
            logger.warning("OCR AI - nie udalo sie ustawic cooldownu w Redis", exc_info=True)
            return 0

    def reset(self, step_label: str) -> None:
        blocked_key, strikes_key = self._keys(step_label)
        try:
            self.client.delete(blocked_key, strikes_key)
        except (RedisError, OSError):
            logger.warning("OCR AI - nie udalo sie wyzerowac cooldownu w Redis", exc_info=True)


@lru_cache(maxsize=1)
def get_ocr_cooldown_store() -> RedisOCRCooldownStore:
    # Polaczenie jest nawiazywane leniwie przy pierwszej operacji, juz wewnatrz procesu workera.
    return RedisOCRCooldownStore(Redis.from_url(settings.redis_url, decode_responses=True))
