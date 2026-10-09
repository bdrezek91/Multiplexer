"""Klient TypeSafe Jev dla Multiplexera.

Na pierwszym etapie Jev dziala w trybie SHADOW:
- nie zmienia wyniku obecnego matchera,
- nie zmienia kodu produktu,
- nie zmienia eksportu TXT,
- sluzy tylko do niezaleznej oceny kandydatow.

Sekrety sa pobierane wylacznie ze zmiennych srodowiskowych.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx


TYPESAFE_SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_REQUEST_TIMEOUT_SECONDS = 6.0


class JevError(RuntimeError):
    """Blad komunikacji lub niepoprawnej odpowiedzi TypeSafe."""


@dataclass(frozen=True)
class JevChoiceResult:
    model: str
    choice: str
    confidence: float
    probabilities: dict[str, float]
    input_tokens: int
    output_tokens: int


def jev_enabled() -> bool:
    return os.getenv("JEV_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def jev_mode() -> str:
    return os.getenv("JEV_MODE", "shadow").strip().lower()


def jev_model() -> str:
    return os.getenv("JEV_MODEL", "jev-latest").strip() or "jev-latest"


async def ask_choice(
    *,
    state: Any,
    question_name: str,
    instructions: Any,
    criteria: dict[str, Any],
) -> JevChoiceResult:
    """Zadaje Jev pojedyncze pytanie typu Choice."""

    api_key = os.getenv("TYPESAFE_API_KEY", "").strip()

    if not api_key:
        raise JevError("Brak TYPESAFE_API_KEY.")

    if not criteria:
        raise JevError("Lista kandydatow Jev jest pusta.")

    payload = {
        "model": jev_model(),
        "state": state,
        "questions": {
            question_name: {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with asyncio.timeout(JEV_REQUEST_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=JEV_REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    TYPESAFE_SYSTEMONE_URL,
                    headers=headers,
                    json=payload,
                )
    except TimeoutError as exc:
        raise JevError(
            f"Timeout Jev po {JEV_REQUEST_TIMEOUT_SECONDS:g} s - zostawiam wynik matchera."
        ) from exc
    except httpx.HTTPError as exc:
        raise JevError(f"Blad polaczenia z TypeSafe: {exc}") from exc

    if response.status_code != 200:
        body = response.text[:1000]
        raise JevError(
            f"TypeSafe HTTP {response.status_code}: {body}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise JevError("TypeSafe zwrocil odpowiedz, ktora nie jest JSON.") from exc

    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise JevError("Brak pola answers w odpowiedzi TypeSafe.")

    answer = answers.get(question_name)
    if not isinstance(answer, dict):
        raise JevError(
            f"Brak odpowiedzi dla pytania {question_name!r}."
        )

    if answer.get("type") != "choice":
        raise JevError(
            f"Nieoczekiwany typ odpowiedzi: {answer.get('type')!r}."
        )

    choice = str(answer.get("choice") or "").strip()

    if not choice:
        raise JevError("Jev nie zwrocil wybranej opcji.")

    try:
        confidence = float(answer.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise JevError("Niepoprawne confidence w odpowiedzi Jev.") from exc

    raw_probabilities = answer.get("probabilities")
    if not isinstance(raw_probabilities, dict):
        raise JevError("Brak probabilities w odpowiedzi Jev.")

    probabilities: dict[str, float] = {}

    for key, value in raw_probabilities.items():
        try:
            probabilities[str(key)] = float(value)
        except (TypeError, ValueError):
            continue

    usage = data.get("usage") or {}

    try:
        input_tokens = int(usage.get("input_tokens") or 0)
    except (TypeError, ValueError):
        input_tokens = 0

    try:
        output_tokens = int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        output_tokens = 0

    return JevChoiceResult(
        model=str(data.get("model") or jev_model()),
        choice=choice,
        confidence=confidence,
        probabilities=probabilities,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
