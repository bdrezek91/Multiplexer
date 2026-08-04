"""Niezalezny drugi odczyt (OpenAI) do wykrywania rozbieznosci z Gemini - realny przypadek
produkcyjny (2026-08-04): to samo zdjecie wydawki dawalo RÓŻNE wyniki ilosci/obecnosci pozycji
miedzy kolejnymi przebiegami Gemini, mimo temperature=0 i podniesionego thinkingLevel (patrz
providers.py, GeminiProvider) - sam prompt nie wyeliminuje kazdego mozliwego bledu modelu.

Gemini pozostaje JEDYNYM zrodlem prawdy zapisywanym do dokumentu i uzywanym do generowania
pliku Optima - OpenAI tutaj WYLACZNIE flaguje niepewne pozycje (needs_review=True + notatka w
form_note), nigdy nie nadpisuje danych ani nie dodaje nowych wierszy samodzielnie (zeby ewentualne
bledy OpenAI nie wplywaly na wynik, tylko go kwestionowaly). Jesli klucz OpenAI nie jest
skonfigurowany (settings.openai_api_key) albo cross-check zawiedzie z jakiegokolwiek powodu -
jest cicho pomijany (best-effort) - awaria/koszt OpenAI nie moze zablokowac calego dokumentu,
ktory i tak konczy sie normalnie na samym Gemini."""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings
from app.modules.matcher.special_rules import SpecialRule
from app.modules.products import Catalog

from .chain import OCRChainStep
from .parsing import parse_float_loose
from .pipeline_elektryka import recognize_document
from .pipeline_hydraulika import recognize_document_hydraulika
from .providers import OpenAIProvider

logger = logging.getLogger(__name__)

_MISMATCH_NOTE = "Niezgodność Gemini/OpenAI (kontrola krzyżowa ilości) - zweryfikuj ręcznie."
_MISSING_NOTE = "OpenAI (kontrola krzyżowa) nie znalazł tej pozycji na dokumencie - zweryfikuj ręcznie."


def _cross_check_chain() -> Optional[list[OCRChainStep]]:
    if not settings.openai_api_key:
        return None
    return [OCRChainStep(
        f"OpenAI {settings.openai_model} (kontrola krzyżowa)",
        OpenAIProvider(), settings.openai_model, settings.openai_api_key,
    )]


def _key_for_pozycja(pozycja: Any) -> str:
    kod = pozycja.match.kod
    return f"kod:{kod}" if kod else f"nazwa:{pozycja.rozpoznana_nazwa.strip().lower()}"


def _key_for_item(item: dict) -> str:
    kod = item.get("match_kod")
    return f"kod:{kod}" if kod else f"nazwa:{item['rozpoznana_nazwa'].strip().lower()}"


def _qty(value: Optional[str]) -> Optional[float]:
    return parse_float_loose(value) if value is not None else None


def _flag(item: dict, note: str) -> None:
    item["needs_review"] = True
    existing = item.get("form_note") or ""
    item["form_note"] = f"{existing} | {note}" if existing else note


def flag_mismatches(items: list[dict], other_pozycje: list) -> None:
    """Modyfikuje `items` (lista dict budowana w tasks.py) W MIEJSCU - ustawia needs_review=True
    i dopisuje notatke do form_note dla kazdej pozycji, ktorej ilosc (wydana/zuzyta) lub sama
    obecnosc nie zgadza sie miedzy Gemini (`items`) a OpenAI (`other_pozycje`). Dopasowanie po
    kodzie z katalogu (nie po indeksie/kolejnosci) - obie strony moga zwrocic pozycje w innej
    kolejnosci badz w innej liczbie."""
    other_by_key: dict[str, Any] = {}
    for p in other_pozycje:
        other_by_key.setdefault(_key_for_pozycja(p), p)

    for item in items:
        other = other_by_key.get(_key_for_item(item))
        if other is None:
            _flag(item, _MISSING_NOTE)
            continue
        if _qty(other.ilosc_wydana) != item["ilosc_wydana"] or _qty(other.ilosc_zuzyta) != item["ilosc_zuzyta"]:
            _flag(item, _MISMATCH_NOTE)


async def run_cross_check(
    files: list[tuple[bytes, str]],
    dzial: str,
    catalog: Catalog,
    magazyn: Optional[str],
    special_rules: Optional[list[SpecialRule]],
    items: list[dict],
) -> None:
    chain = _cross_check_chain()
    if chain is None:
        return
    try:
        if dzial == "hydraulika":
            result = await recognize_document_hydraulika(files, catalog, magazyn=magazyn, chain=chain)
        else:
            result = await recognize_document(files, catalog, special_rules or [], magazyn=magazyn, chain=chain)
    except Exception as exc:  # best-effort - awaria/koszt OpenAI NIE moze zepsuc calego dokumentu
        logger.warning("Cross-check OpenAI pominięty - błąd: %s", exc, extra={"dzial": dzial})
        return

    # Log diagnostyczny (2026-08-04: gpt-4o-mini na produkcji znajdowal ulamek pozycji Gemini,
    # co bez tego logu bylo niemozliwe odroznic od realnych rozbieznosci ilosci - patrz komentarz
    # przy settings.openai_model) - liczba pozycji po obu stronach, PRZED probą dopasowania.
    logger.info(
        "Cross-check OpenAI zakończony", extra={
            "dzial": dzial, "pozycje_gemini": len(items), "pozycje_openai": len(result.pozycje),
        },
    )
    flag_mismatches(items, result.pozycje)
