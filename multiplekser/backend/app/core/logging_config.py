"""Strukturalne logowanie (Etap "quick winy" - 2026-07-30). Dotad backend prawie nic nie
zapisywal o tym, co dzieje sie w srodku (logowania, bledy OCR w tle w Celery, wyjatki -
logger.exception() w main.py z Etapu 1 lecial donikad, bo nic nie konfigurowalo root loggera).

Format: jeden obiekt JSON na linie (stdout) - latwy do parsowania przez `docker compose logs`,
`jq`, albo dowolny agregator logow (Loki/CloudWatch/itp.), bez potrzeby wdrazania czegokolwiek
dodatkowego teraz. To 12-factor app: loguj na stdout, o przechowywanie/agregacje niech zadba
infrastruktura, nie sama aplikacja (wiec zadnych plikow logow, zadnego RotatingFileHandler).

`configure_logging()` wolane raz w kazdym z dwoch procesow, ktore maja wlasny root logger:
API (app/main.py) i worker Celery (app/core/celery_app.py) - to osobne procesy, konfiguracja
w jednym nie dotyczy drugiego."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Pola przekazane przez `logger.info(..., extra={...})` - np. user_id, document_id.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging() -> None:
    from app.core.config import settings

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    # Idempotentne - w testach/reloaderze modul moze zaimportowac sie wielokrotnie, bez tego
    # kazde wywolanie dokladaloby kolejny handler i logi dublowalyby sie w nieskonczonosc.
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
