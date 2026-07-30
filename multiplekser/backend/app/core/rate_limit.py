"""Rate limiting (Etap "quick winy" - 2026-07-30) - ochrona /auth/token przed brute-force
(bez tego nic nie stalo na przeszkodzie, zeby probowac tysiace hasel na sekunde).

Magazyn Redis, NIE domyslny in-memory slowapi - produkcja odpala WEB_CONCURRENCY=2 (i wiecej)
osobnych procesow uvicorn (patrz docker-compose.prod.yml), a in-memory liczniki sa per-proces,
wiec efektywny limit bylby N razy wiekszy niz zamierzony (kazdy proces liczylby osobno). Redis
jest juz w stosie (broker Celery), wiec zero nowej infrastruktury - tylko settings.redis_url."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
