"""Aplikacja Celery (Etap 7) - kolejka dla zadan dlugotrwalych (OCR), zgodnie z CLAUDE.md
regula 6: "operacje dlugotrwale asynchronicznie przez Celery, nigdy blokujaco w zadaniu HTTP".

Uruchomienie workera:
    celery -A app.core.celery_app worker --loglevel=info
"""
from celery import Celery

from app.core.config import settings
from app.core.logging_config import configure_logging

# Osobny proces od API (app/main.py) - ma wlasny root logger, wiec potrzebuje wlasnego wywolania
# configure_logging() (patrz app/core/logging_config.py).
configure_logging()

# Import jawny wszystkich modeli ORM (nie poleganie na przypadkowym imporcie) - PRZED
# skonfigurowaniem workera. Proces workera Celery importuje tylko to, co ponizej (nie caly
# main.py jak proces API), wiec bez tego SQLAlchemy nie potrafi rozwiazac string-owych FK
# (np. `ForeignKey("app_user.id")` w DocumentModel) przy pierwszej operacji ORM w workerze -
# ten sam blad, ktory naprawiono juz raz w tests/conftest.py (Etap 5), tu w innym procesie.
from app.modules.matcher import models as _matcher_models  # noqa: F401
from app.modules.products import models as _products_models  # noqa: F401
from app.modules.users import models as _users_models  # noqa: F401
from app.modules.documents import models as _documents_models  # noqa: F401

celery_app = Celery("multiplekser", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
)

# Rejestruje taski zdefiniowane w modulach (import ma efekt uboczny - podpina @celery_app.task).
celery_app.autodiscover_tasks(["app.modules.documents"])
