"""Zbiorcza, semantyczna kontrola ilosci pominietych przez glowny OCR.

Wszystkie niejasne wiersze trafiaja do jednego zapytania na model, zawsze na PELNYM,
niezmienionym obrazie dokumentu (bez wycinania konkretnych wierszy - patrz nizej dlaczego).
Odpowiedz z samymi null NIE jest sukcesem: taki model zostaje odrzucony, a nierozpoznane
pozycje przechodza zbiorczo do nastepnego kroku lancucha.

Wczesniej ta funkcja (przez verification_image.py: prepare_verification_files) probowala
wycinac z obrazu konkretny wiersz na podstawie zakodowanego na sztywno, domniemanego ukladu
fizycznego kartki (numer strony + numer wiersza per nazwa pozycji). Usuniete calkowicie
(2026-08-31, na zyczenie uzytkownika) - papierowa wydawka rozni sie za kazdym razem (rozne
wersje formularza, rozne rewizje z biegiem czasu), wiec jakikolwiek sztywny uklad wierszy jest
z zalozenia niemozliwy do trwalego utrzymania. Trzy kolejne, coraz gorsze awarie tego samego typu
w Hydraulice (patrz docs/RAPORT_OCR_NIEZAWODNOSC_3.md, _4.md) i potwierdzone ~55% braku pokrycia
w mapie dla Elektryki (153 pozycje w aktualnym szablonie vs 69 w mapie wycinkow) pokazaly, ze to
nie byl przypadek do punktowej naprawy, tylko zle zalozenie architektoniczne. Kontrola dziala
teraz zawsze na pelnym obrazie - mniej precyzyjne "zoomowanie" przy bardzo zageszczonych
kartkach, ale zero ryzyka zlego dopasowania wiersza.

Lancuch (`quantity_verification_chain()`, patrz chain.py) jest na zyczenie uzytkownika (2026-08-07)
WYLACZNIE darmowy - pozycja, ktorej nie odczyta zaden z czterech darmowych modeli Gemini, zostaje
"Bez wyniku" (patrz `_publish_no_result`) i wymaga recznej weryfikacji na oryginale, bez placonego
fallbacku (inaczej niz `default_ocr_chain()` uzywany do pelnego odczytu calego dokumentu).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional

from .chain import (
    AllProvidersFailedError,
    OCRChainEventCallback,
    quantity_verification_chain,
    run_ocr_chain,
)
from .cooldown import OCRCooldownStore
from .parsing import extract_json, parse_float_loose

_NO_QUANTITY_REASON = "model nie odczytal zadnej ilosci dla sprawdzanych pozycji"


@dataclass
class VerifyResult:
    ilosc_wydana: Optional[float]
    ilosc_zuzyta: Optional[float]

    @property
    def found_anything(self) -> bool:
        return self.ilosc_wydana is not None or self.ilosc_zuzyta is not None


def _quantity(value: object) -> float | None:
    if value in (None, ""):
        return None
    parsed = parse_float_loose(value)
    return parsed if parsed is not None and parsed > 0 else None


def _parse_batch_response(text: str, expected_ids: set[str]) -> dict[str, VerifyResult]:
    parsed = extract_json(text)
    raw_items = parsed.get("pozycje") if isinstance(parsed, dict) else None
    if not isinstance(raw_items, list):
        return {}

    results: dict[str, VerifyResult] = {}
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id", "")).strip()
        if item_id not in expected_ids:
            continue
        result = VerifyResult(
            ilosc_wydana=_quantity(raw.get("ilosc_wydana")),
            ilosc_zuzyta=_quantity(raw.get("ilosc_zuzyta")),
        )
        if result.found_anything:
            results[item_id] = result
    return results


def _build_prompt(targets: list[tuple[str, str]], cropped: bool) -> str:
    target_lines = "\n".join(f'- ID {item_id}: "{name.replace(chr(34), chr(39))}"' for item_id, name in targets)
    source_hint = (
        "Otrzymujesz jeden obraz z osobnymi wycinkami. Kazdy wycinek ma etykiete 'Cel ID'. "
        "Kazdy wycinek zawiera WYLACZNIE jeden docelowy wiersz: jego nazwe i komorki ilosci. "
        "Nie ma na nim wierszy sasiednich."
        if cropped else
        "Otrzymujesz oryginalny dokument. Znajdz ponizsze wiersze po pelnej nazwie; podobne "
        "wiersze obok nie sa tym samym materialem."
    )
    return f"""Jestes przemyslowym silnikiem OCR do dokumentow magazynowych.
{source_hint}

Sprawdz WYŁĄCZNIE te pozycje:
{target_lines}

Dla kazdego ID odczytaj OSOBNO kolumny "Ilosc wydana" i "Ilosc zuzyta". Ptaszek/haczyk/V/✓
nie jest liczba, ale cyfra i ptaszek czesto stoja razem. Jesli obok ptaszka widac odrebna cyfre
(takze 1), zwroc te cyfre. Nie przenos wartosci z sasiedniego wiersza.

Zwroc WYLACZNIE JSON, zachowujac ID:
{{"pozycje":[{{"id":"1","ilosc_wydana":2,"ilosc_zuzyta":null}}]}}
Jesli dla konkretnego ID naprawde nie ma czytelnej cyfry, zwroc dla niego oba pola null."""


def _publish_no_result(
    unresolved: list[tuple[str, str]], event_callback: Optional[OCRChainEventCallback],
) -> None:
    if not unresolved or event_callback is None:
        return
    names = ", ".join(name for _, name in unresolved)
    try:
        event_callback({
            "status": "no_result",
            "stage": "quantity_verification",
            "provider": None,
            "model": None,
            "label": None,
            "reason": f"Nie znaleziono ilosci dla: {names}",
            "step": None,
            "total_steps": None,
            "duration_ms": None,
            "attempt": None,
            "target": names,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        # To tylko log dla UI; zapis nie moze uniewaznic poprawnie zakonczonego OCR.
        return


async def verify_ambiguous_quantities(
    files: list[tuple[bytes, str]], names: list[str], dzial: str,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> list[VerifyResult]:
    """Sprawdza wszystkie nazwy zbiorczo i zwraca wyniki w tej samej kolejnosci."""
    targets = [(str(index + 1), name) for index, name in enumerate(names)]
    if not targets:
        return []

    # Zawsze pelny, niezmieniony obraz - patrz docstring modulu, dlaczego wycinanie
    # konkretnych wierszy zostalo calkowicie usuniete.
    verification_files, cropped = files, False
    unresolved = dict(targets)
    found: dict[str, VerifyResult] = {}
    steps = quantity_verification_chain()

    for step_index, step in enumerate(steps):
        if not unresolved:
            break
        current_targets = list(unresolved.items())
        expected_ids = set(unresolved)
        prompt = _build_prompt(current_targets, cropped)
        target_label = ", ".join(unresolved.values())[:500]
        try:
            chain_result = await run_ocr_chain(
                verification_files,
                prompt,
                chain=[step],
                response_validator=lambda text, ids=expected_ids: bool(
                    _parse_batch_response(text, ids)
                ),
                log_context={
                    **dict(log_context or {}),
                    "ai_stage": "quantity_verification",
                    "ai_target": target_label,
                },
                event_callback=event_callback,
                cooldown_store=cooldown_store,
                invalid_response_reason=_NO_QUANTITY_REASON,
                chain_position_offset=step_index,
                chain_total_steps=len(steps),
                publish_terminal_failure=False,
            )
        except AllProvidersFailedError:
            continue

        parsed_results = _parse_batch_response(chain_result.text, expected_ids)
        for item_id, result in parsed_results.items():
            found[item_id] = result
            unresolved.pop(item_id, None)

    _publish_no_result(list(unresolved.items()), event_callback)
    return [found.get(item_id, VerifyResult(None, None)) for item_id, _ in targets]


async def verify_ambiguous_quantity(
    files: list[tuple[bytes, str]], nazwa: str,
    log_context: Optional[Mapping[str, object]] = None,
    event_callback: Optional[OCRChainEventCallback] = None,
    cooldown_store: Optional[OCRCooldownStore] = None,
) -> VerifyResult:
    """Wstecznie zgodny wrapper dla pojedynczego wiersza."""
    results = await verify_ambiguous_quantities(
        files, [nazwa], "elektryka", log_context, event_callback, cooldown_store,
    )
    return results[0]
