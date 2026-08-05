"""Klasyfikacja dzialu dokumentu (Krok Hydraulika-3) - NOWA praca, nie port z zadnego monolitu
(oba monolity - Elektryka i Hydraulika - byly osobnymi aplikacjami, zaden z nich nie klasyfikowal
niczego). Realizuje dwuetapowe wywolanie Gemini z docs/MIGRATION_PLAN_HYDRAULIKA.md (sekcja 4.5):
Krok A (tu) - tani, szybki request z samym pytaniem "jaki to dzial", bez schematu pozycji.
Krok B - pelny odczyt promptem juz dopasowanym do wykrytego dzialu (patrz ocr/pipeline.py i
ocr/pipeline_hydraulika.py).

Uzytkownik nie chce recznego przelacznika dzialu w UI - klasyfikacja MUSI byc w pelni
automatyczna. Jesli odpowiedz modelu nie da sie sparsowac na jednoznaczne "elektryka"/
"hydraulika" (np. model nie zwrocil poprawnego JSON), pada bezpieczny fallback na "elektryka"
z confidence=0.0 - to jedyny dzial obslugiwany przed tym krokiem, wiec zachowuje dotychczasowe
zachowanie zamiast losowo zgadywac nowy dzial.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from .chain import AllProvidersFailedError, OCRChainEventCallback, OCRChainStep, run_ocr_chain
from .parsing import extract_json

CLASSIFY_PROMPT = (
    'Jesteś klasyfikatorem dokumentów magazynowych. Na obrazie (lub obrazach, jeśli dostajesz '
    'więcej niż jeden - to kolejne strony TEGO SAMEGO dokumentu, nie osobne dokumenty) / w PDF '
    'jest formularz wydania materiałów z nagłówkiem, w którym jedno z pól to nazwa działu - '
    'dokładnie "Elektryka" lub "Hydraulika" (czasem odręcznie, czasem drukowane). Nagłówek '
    'zwykle jest tylko na pierwszej stronie. Odczytaj WYŁĄCZNIE tę wartość, nie analizuj tabeli '
    'pozycji ani innych pól nagłówka.\n\n'
    'Zwróć WYŁĄCZNIE obiekt JSON, bez markdown, bez komentarzy: '
    '{"dzial":"elektryka","confidence":97.5} albo {"dzial":"hydraulika","confidence":88.0}. '
    'Pole "dzial" MUSI być dokładnie jedną z tych dwóch wartości (małymi literami, bez polskich '
    'znaków). Jeśli nie masz pewności, wybierz bardziej prawdopodobną wartość i ustaw niższe '
    '"confidence" - nigdy nie zwracaj null ani żadnej innej wartości pola "dzial".'
)

_VALID_DZIALY = ("elektryka", "hydraulika")
_FALLBACK_DZIAL = "elektryka"


def _is_valid_classification_response(text: str) -> bool:
    parsed = extract_json(text)
    if not isinstance(parsed, dict):
        return False
    return str(parsed.get("dzial") or "").strip().lower() in _VALID_DZIALY


@dataclass
class ClassifyResult:
    dzial: str
    confidence: float
    used_provider: str
    fallback: bool = False


async def classify_document(
    files: list[tuple[bytes, str]], chain: Optional[list[OCRChainStep]] = None,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
) -> ClassifyResult:
    # thinking_level="low" (2026-08-04, na zyczenie uzytkownika - przetwarzanie calego dokumentu
    # trwalo 2-3 minuty) - to trywialna decyzja (jedno pole naglowka), nie potrzebuje glebszego
    # rozumowania jak pelny odczyt tabeli (patrz GeminiProvider.recognize) - a jest PIERWSZYM z
    # dwoch sekwencyjnych zapytan, wiec kazda sekunda tutaj przeklada sie wprost na czas calosci.
    try:
        chain_result = await run_ocr_chain(
            files, CLASSIFY_PROMPT, chain=chain, thinking_level="low",
            response_validator=_is_valid_classification_response,
            log_context={**dict(log_context or {}), "ai_stage": "classification"},
            event_callback=event_callback,
        )
    except AllProvidersFailedError as exc:
        # Zachowujemy bezpieczny fallback, ale dopiero po sprawdzeniu pozostalych modeli.
        if exc.last_invalid_text is not None:
            return ClassifyResult(
                dzial=_FALLBACK_DZIAL, confidence=0.0,
                used_provider=exc.last_invalid_label or "brak poprawnej odpowiedzi", fallback=True,
            )
        raise
    parsed = extract_json(chain_result.text)

    dzial = None
    confidence = 0.0
    if isinstance(parsed, dict):
        raw_dzial = str(parsed.get("dzial") or "").strip().lower()
        if raw_dzial in _VALID_DZIALY:
            dzial = raw_dzial
        try:
            confidence = float(parsed.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0.0

    if dzial is None:
        return ClassifyResult(
            dzial=_FALLBACK_DZIAL, confidence=0.0, used_provider=chain_result.used_label, fallback=True,
        )
    return ClassifyResult(dzial=dzial, confidence=confidence, used_provider=chain_result.used_label)
