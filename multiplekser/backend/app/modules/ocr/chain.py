"""Lancuch dostawcow z automatycznym fallbackiem - port AI_CHAIN + petli prob w runAI() z monolitu.

Dwa warianty lancucha, obydwa budowane na biezaco z `settings` (patrz kazda funkcja):
- `default_ocr_chain()` - pelny odczyt pozycji z dokumentu (pipeline_elektryka/hydraulika,
  verify.py). Kolejnosc prob (2026-08-04): cztery modele Gemini na kluczu darmowym (3.6 Flash,
  3.5 Flash, 3.5 Flash Lite i 3.1 Flash Lite) -> Gemini 3.6 Flash na kluczu platnym -> OpenAI na
  kluczu platnym (ostatni krok, uzywany WYLACZNIE gdy wszystkie kroki Gemini zawioda - nie przy
  kazdym dokumencie). Tu liczy sie przede wszystkim jakosc, wiec zaczynamy od najmocniejszego
  modelu.
- `classify_ocr_chain()` - sama klasyfikacja dzialu (ocr/classify.py, Krok A), zadanie na tyle
  proste (jedno pole tekstowe z naglowka), ze zaczyna od NAJSLABSZEGO/najtanszego modelu Gemini,
  zeby nie marnowac zasobow mocniejszych modeli na ten krok; fallback dalej przez te same
  modele/klucze co wyzej.

Osobny mechanizm cross-checku OpenAI (rownolegly drugi odczyt przy KAZDYM dokumencie, patrz git
historia ocr/crosscheck.py) zostal porzucony, bo w praktyce dawal duzo szumu (falszywe "nie
znaleziono pozycji") i byl bardziej kosztowny niz prosty fallback na koncu tego samego lancucha.

Blad dowolnego kroku (429/401/403/timeout/5xx/brak sieci) automatycznie przelacza na kolejny
krok. Krok bez skonfigurowanego klucza jest pomijany (nie liczy sie jako "blad" - odpowiednik
`skipped.push(...)` w monolicie). Lancuch jest bezstanowy - kazde wywolanie startuje od poczatku
(bez pamieci ktory dostawca ostatnio zadzialal).
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from app.core.config import settings

from .cooldown import OCRCooldownStore
from .providers import GeminiProvider, OCRProvider, OCRProviderError, OpenAIProvider

logger = logging.getLogger(__name__)

_INVALID_RESPONSE_REASON = "odpowiedz nie spelnia wymagan formatu lub schematu"
_MAX_LOGGED_REASON_LENGTH = 500

OCRChainEventCallback = Callable[[dict[str, object]], None]


@dataclass
class OCRChainStep:
    label: str
    provider: OCRProvider
    model: str
    api_key: Optional[str]


def default_ocr_chain() -> list[OCRChainStep]:
    """Buduje lancuch na podstawie AKTUALNYCH ustawien (nie stala modulu) - zeby zmiana
    zmiennych srodowiskowych (klucze) byla widoczna bez restartu importu tego modulu."""
    gemini = GeminiProvider()
    free_key = settings.gemini_api_key_free
    paid_key = settings.gemini_api_key_paid
    return [
        OCRChainStep("Gemini 3.6 Flash (klucz darmowy)", gemini, "gemini-3.6-flash", free_key),
        OCRChainStep("Gemini 3.5 Flash (klucz darmowy)", gemini, "gemini-3.5-flash", free_key),
        OCRChainStep("Gemini 3.5 Flash Lite (klucz darmowy)", gemini, "gemini-3.5-flash-lite", free_key),
        OCRChainStep("Gemini 3.1 Flash Lite (klucz darmowy)", gemini, "gemini-3.1-flash-lite", free_key),
        OCRChainStep("Gemini 3.6 Flash (klucz platny)", gemini, "gemini-3.6-flash", paid_key),
        OCRChainStep(
            f"OpenAI {settings.openai_model} (klucz platny)",
            OpenAIProvider(), settings.openai_model, settings.openai_api_key,
        ),
    ]


def classify_ocr_chain() -> list[OCRChainStep]:
    """Lancuch dla samej klasyfikacji dzialu (Krok A z ocr/classify.py) - to zadanie jest
    bardzo proste (odczytanie jednego pola tekstowego z naglowka), wiec w odroznieniu od
    `default_ocr_chain()` (uzywanego do pelnego odczytu pozycji, gdzie na pierwszym miejscu
    liczy sie jakosc) zaczynamy od NAJSLABSZEGO/najtanszego modelu Gemini na kluczu darmowym,
    zeby nie marnowac zasobow mocniejszych modeli na tak prosty krok. Fallback nadal przechodzi
    przez te same modele/klucze co domyslny lancuch (w razie bledu/przeciazenia), z tym samym
    ostatecznym zabezpieczeniem na OpenAI jako ostatni krok."""
    gemini = GeminiProvider()
    free_key = settings.gemini_api_key_free
    paid_key = settings.gemini_api_key_paid
    return [
        OCRChainStep("Gemini 3.1 Flash Lite (klucz darmowy)", gemini, "gemini-3.1-flash-lite", free_key),
        OCRChainStep("Gemini 3.5 Flash Lite (klucz darmowy)", gemini, "gemini-3.5-flash-lite", free_key),
        OCRChainStep("Gemini 3.5 Flash (klucz darmowy)", gemini, "gemini-3.5-flash", free_key),
        OCRChainStep("Gemini 3.6 Flash (klucz darmowy)", gemini, "gemini-3.6-flash", free_key),
        OCRChainStep("Gemini 3.6 Flash (klucz platny)", gemini, "gemini-3.6-flash", paid_key),
        OCRChainStep(
            f"OpenAI {settings.openai_model} (klucz platny)",
            OpenAIProvider(), settings.openai_model, settings.openai_api_key,
        ),
    ]


class AllProvidersFailedError(Exception):
    def __init__(
        self, skipped: list[str], last_error: Optional[Exception],
        last_invalid_text: Optional[str] = None, last_invalid_label: Optional[str] = None,
    ):
        self.skipped = skipped
        self.last_error = last_error
        self.last_invalid_text = last_invalid_text
        self.last_invalid_label = last_invalid_label
        if last_error is None:
            msg = "Nie podano zadnego klucza API - uzupelnij co najmniej jeden klucz Gemini."
        else:
            msg = f"Wszyscy dostawcy zawiedli. Ostatni blad: {last_error}"
            if skipped:
                msg += f" | pominieto: {', '.join(skipped)}"
        super().__init__(msg)


@dataclass
class OCRChainResult:
    text: str
    used_label: str


def _provider_name(step: OCRChainStep) -> str:
    return step.provider.__class__.__name__.removesuffix("Provider")


def _safe_reason(exc: Exception) -> str:
    """Krotki powod do logu, bez prompta ani pelnej odpowiedzi modelu."""
    reason = " ".join(str(exc).split())
    return reason[:_MAX_LOGGED_REASON_LENGTH]


def _step_log_context(
    step: OCRChainStep, step_number: int, total_steps: int,
    log_context: Optional[Mapping[str, object]],
) -> dict[str, object]:
    extra = dict(log_context or {})
    # Pola lancucha maja pierwszenstwo, zeby przypadkowy kontekst wolajacego nie mogl
    # podmienic modelu/dostawcy widocznego w logu.
    extra.update({
        "ai_provider": _provider_name(step),
        "ai_model": step.model,
        "ai_label": step.label,
        "chain_step": step_number,
        "chain_steps": total_steps,
    })
    return extra


def _publish_event(
    status: str,
    extra: Mapping[str, object],
    event_callback: Optional[OCRChainEventCallback],
) -> None:
    """Przekazuje bezpieczny podzbior danych do trwalego dziennika dokumentu.

    Prompt, odpowiedz modelu, pliki i klucz API celowo nigdy nie trafiaja do payloadu.
    Awaria opcjonalnego zapisu dziennika nie moze przerwac wlasciwego OCR.
    """
    if event_callback is None:
        return
    event = {
        "status": status,
        "stage": extra.get("ai_stage"),
        "provider": extra.get("ai_provider"),
        "model": extra.get("ai_model"),
        "label": extra.get("ai_label"),
        "reason": extra.get("reason") or extra.get("last_reason"),
        "step": extra.get("chain_step"),
        "total_steps": extra.get("chain_steps"),
        "duration_ms": extra.get("duration_ms"),
        "attempt": extra.get("ocr_attempt"),
        "target": extra.get("ai_target"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        event_callback(event)
    except Exception:
        logger.exception(
            "OCR AI - nie udalo sie zapisac zdarzenia dla strony",
            extra={"document_id": extra.get("document_id"), "event_status": status},
        )


async def run_ocr_chain(
    files: list[tuple[bytes, str]], prompt: str, chain: Optional[list[OCRChainStep]] = None,
    thinking_level: str = "low", response_validator: Optional[Callable[[str], bool]] = None,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
    invalid_response_reason: str = _INVALID_RESPONSE_REASON,
    chain_position_offset: int = 0,
    chain_total_steps: Optional[int] = None,
    publish_terminal_failure: bool = True,
) -> OCRChainResult:
    """Przejscie po lancuchu: pierwszy dostawca z kluczem, ktory odpowie poprawnie, wygrywa.
    `files` - lista (bytes, mime), patrz OCRProvider.recognize. `thinking_level` - patrz
    GeminiProvider.recognize(); domyslnie "low" dla wszystkich etapow OCR, aby ograniczyc czas
    odpowiedzi. Wolajacy nadal moze jawnie wybrac inny poziom dla pojedynczego zadania.
    `response_validator` odrzuca odpowiedz HTTP 200 w zlym formacie i uruchamia kolejny krok.
    `log_context` pozwala dopiac np. document_id i etap OCR bez logowania prompta/pliku/klucza.
    `event_callback` zapisuje ten sam bezpieczny slad do widoku dokumentu. `cooldown_store`
    pomija modele czasowo zablokowane po API 429 (w produkcji wspolny Redis)."""
    steps = chain if chain is not None else default_ocr_chain()
    total_steps = chain_total_steps if chain_total_steps is not None else len(steps)
    last_error: Optional[Exception] = None
    last_invalid_text: Optional[str] = None
    last_invalid_label: Optional[str] = None
    skipped: list[str] = []

    first_active = next((step for step in steps if step.api_key), None)
    start_extra = dict(log_context or {})
    start_extra.update({
        "first_ai_provider": _provider_name(first_active) if first_active else None,
        "first_ai_model": first_active.model if first_active else None,
        "first_ai_label": first_active.label if first_active else None,
        "chain_steps": total_steps,
        "configured_steps": sum(bool(step.api_key) for step in steps),
        "file_count": len(files),
        "thinking_level": thinking_level,
    })
    logger.info("OCR AI - start lancucha modeli", extra=start_extra)

    for step_number, step in enumerate(steps, start=1 + chain_position_offset):
        step_extra = _step_log_context(step, step_number, total_steps, log_context)
        if not step.api_key:
            skipped.append(f"{step.label} (brak klucza)")
            logger.info(
                "OCR AI - model pominiety",
                extra={**step_extra, "reason": "brak skonfigurowanego klucza API"},
            )
            _publish_event(
                "skipped",
                {**step_extra, "reason": "brak skonfigurowanego klucza API"},
                event_callback,
            )
            continue
        remaining_seconds = cooldown_store.remaining_seconds(step.label) if cooldown_store else 0
        if remaining_seconds > 0:
            remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
            reason = f"blokada po API 429, pozostalo ok. {remaining_minutes} min"
            skipped.append(f"{step.label} ({reason})")
            logger.info("OCR AI - model pominiety", extra={**step_extra, "reason": reason})
            _publish_event("skipped", {**step_extra, "reason": reason}, event_callback)
            continue
        started_at = time.monotonic()
        logger.info("OCR AI - proba modelu", extra=step_extra)
        _publish_event("attempt", step_extra, event_callback)
        try:
            text = await step.provider.recognize(
                files=files, model=step.model, api_key=step.api_key, prompt=prompt,
                thinking_level=thinking_level,
            )
            if response_validator is not None and not response_validator(text):
                last_invalid_text = text
                last_invalid_label = step.label
                last_error = OCRProviderError(
                    f"{step.label} zwrocil odpowiedz w niepoprawnym formacie"
                )
                logger.warning(
                    "OCR AI - odpowiedz modelu odrzucona",
                    extra={
                        **step_extra,
                        "reason": invalid_response_reason,
                        "error_type": "ResponseValidationError",
                        "duration_ms": round((time.monotonic() - started_at) * 1000),
                    },
                )
                _publish_event(
                    "rejected",
                    {
                        **step_extra,
                        "reason": invalid_response_reason,
                        "duration_ms": round((time.monotonic() - started_at) * 1000),
                    },
                    event_callback,
                )
                continue
            logger.info(
                "OCR AI - wybrano model",
                extra={
                    **step_extra,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
            )
            if cooldown_store:
                cooldown_store.reset(step.label)
            _publish_event(
                "selected",
                {
                    **step_extra,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
                event_callback,
            )
            return OCRChainResult(text=text, used_label=step.label)
        except OCRProviderError as exc:
            last_error = exc
            reason = _safe_reason(exc)
            if exc.status_code == 429:
                # Pelne body bledu Google jest dlugie i malo czytelne w panelu dokumentu.
                # Wystarcza kod + konkretna decyzja systemu; surowej odpowiedzi nie zapisujemy.
                reason = "Przekroczony limit zapytan API (429)"
                if cooldown_store:
                    cooldown_minutes = cooldown_store.record_rate_limit(step.label)
                    if cooldown_minutes:
                        reason = f"{reason} | blokada modelu na {cooldown_minutes} min"
            logger.warning(
                "OCR AI - model odrzucony",
                extra={
                    **step_extra,
                    "reason": reason,
                    "error_type": type(exc).__name__,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
            )
            _publish_event(
                "rejected",
                {
                    **step_extra,
                    "reason": reason,
                    "duration_ms": round((time.monotonic() - started_at) * 1000),
                },
                event_callback,
            )
            continue

    failure_extra = dict(log_context or {})
    failure_extra.update({
        "attempted_steps": len(steps) - len(skipped),
        "skipped_steps": len(skipped),
        "last_reason": _safe_reason(last_error) if last_error else "brak skonfigurowanego klucza API",
    })
    logger.error("OCR AI - wszystkie modele zawiodly", extra=failure_extra)
    if publish_terminal_failure:
        _publish_event("failed", failure_extra, event_callback)
    raise AllProvidersFailedError(
        skipped=skipped, last_error=last_error,
        last_invalid_text=last_invalid_text, last_invalid_label=last_invalid_label,
    )
