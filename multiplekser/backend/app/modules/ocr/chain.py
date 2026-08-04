"""Lancuch dostawcow z automatycznym fallbackiem - port AI_CHAIN + petli prob w runAI() z monolitu.

Kolejnosc prob: cztery modele Gemini na kluczu darmowym (limity RPM/RPD liczone osobno na model
w obrebie projektu Google, wiec to cztery niezalezne dzienne pule) -> Gemini 3.6 Flash na kluczu
platnym. Blad dowolnego kroku (429/401/403/timeout/5xx/brak sieci) automatycznie przelacza na
kolejny krok. Krok bez skonfigurowanego klucza jest pomijany (nie liczy sie jako "blad" -
odpowiednik `skipped.push(...)` w monolicie). Lancuch jest bezstanowy - kazde wywolanie startuje
od poczatku (bez pamieci ktory dostawca ostatnio zadzialal).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings

from .providers import GeminiProvider, OCRProvider, OCRProviderError


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
        OCRChainStep("Gemini 3.5 Flash-Lite (klucz darmowy)", gemini, "gemini-3.5-flash-lite", free_key),
        OCRChainStep("Gemini 3.1 Flash-Lite (klucz darmowy)", gemini, "gemini-3.1-flash-lite", free_key),
        OCRChainStep("Gemini 3.6 Flash (klucz platny)", gemini, "gemini-3.6-flash", paid_key),
    ]


class AllProvidersFailedError(Exception):
    def __init__(self, skipped: list[str], last_error: Optional[Exception]):
        self.skipped = skipped
        self.last_error = last_error
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


async def run_ocr_chain(
    files: list[tuple[bytes, str]], prompt: str, chain: Optional[list[OCRChainStep]] = None,
) -> OCRChainResult:
    """Przejscie po lancuchu: pierwszy dostawca z kluczem, ktory odpowie poprawnie, wygrywa.
    `files` - lista (bytes, mime), patrz OCRProvider.recognize."""
    steps = chain if chain is not None else default_ocr_chain()
    last_error: Optional[Exception] = None
    skipped: list[str] = []

    for step in steps:
        if not step.api_key:
            skipped.append(f"{step.label} (brak klucza)")
            continue
        try:
            text = await step.provider.recognize(
                files=files, model=step.model, api_key=step.api_key, prompt=prompt,
            )
            return OCRChainResult(text=text, used_label=step.label)
        except OCRProviderError as exc:
            last_error = exc
            continue

    raise AllProvidersFailedError(skipped=skipped, last_error=last_error)
