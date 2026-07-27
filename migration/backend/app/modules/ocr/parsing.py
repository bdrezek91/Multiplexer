"""Parsowanie i walidacja odpowiedzi AI - port 1:1 extractJSON()/validAIItem() z monolitu."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE_RE = re.compile(r"```json|```")

# Port JS parseFloat(): parsuje wiodacy fragment liczbowy, ignoruje "smiecie" po nim
# (np. "5 szt" -> 5.0), w przeciwienstwie do Pythonowego float() ktory rzucilby wyjatek.
# Celowo NIE rozumie polskiego przecinka dziesietnego - dokladnie tak samo "naiwny" jak
# oryginalny JS (parseFloat("12,5") tez zwraca 12, nie 12.5).
_PARSE_FLOAT_RE = re.compile(r"^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")


def _parse_float_loose(value: Any) -> Optional[float]:
    match = _PARSE_FLOAT_RE.match(str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def extract_json(text: Optional[str]) -> Any:
    """Modele (zwlaszcza darmowe) czesto owijaja JSON tekstem/markdownem - wycina sam obiekt/tablice."""
    t = _FENCE_RE.sub("", text or "").strip()
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        pass

    io1, ia = t.find("{"), t.find("[")
    start = ia if io1 == -1 else (io1 if ia == -1 else min(io1, ia))
    if start == -1:
        return None
    end_b, end_a = t.rfind("}"), t.rfind("]")
    end = max(end_b, end_a)
    if end <= start:
        return None
    try:
        return json.loads(t[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def validate_item(item: Any) -> bool:
    """Wpisy niezgodne ze schematem sa odrzucane zamiast psuc tabele (patrz runAI() w monolicie)."""
    if not isinstance(item, dict):
        return False
    nazwa = item.get("nazwa")
    if not isinstance(nazwa, str) or len(nazwa.strip()) < 2:
        return False
    for field in ("ilosc_wydana", "ilosc_zuzyta", "ilosc"):
        value = item.get(field)
        if value is not None and value != "" and _parse_float_loose(value) is None:
            return False
    return True
