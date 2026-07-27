"""Wynik dopasowania - wydzielone z core.py zeby special_rules.py mogl go uzywac bez cyklu importow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

QUALITY_OK = "ok"
QUALITY_WARN = "warn"
QUALITY_BAD = "bad"
QUALITY_EXCLUDED = "excluded"


@dataclass
class MatchResult:
    kod: Optional[str]
    nazwa: Optional[str]
    quality: str
    ratio: float
    jm_override: Optional[str] = None
