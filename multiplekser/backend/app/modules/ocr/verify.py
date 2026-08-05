"""Druga, waska proba odczytu ilosci - patrz docs/RAPORT_OCR_NIEZAWODNOSC_1.md.

Uruchamiana WYLACZNIE dla pozycji, ktore po glownym przebiegu maja PUSTA ilosc w OBU kolumnach
(ilosc_wydana i ilosc_zuzyta = null), mimo ze pozycja i tak trafila do wyniku (model wykryl w
tym wierszu cos realnego - samo puste-w-obu-kolumnach jest juz pomijane calkowicie na etapie
glownego promptu). Typowy przypadek: cyfra "1" nierozroznialna od ptaszka potwierdzenia przy
pierwszym, calodokumentowym przebiegu - druga proba z waskim, ukierunkowanym pytaniem o JEDEN
konkretny wiersz bywa skuteczniejsza.

Ograniczenie: dziala na CALYM obrazie, nie na wycietym fragmencie komorki - system nie ma
wspolrzednych/bounding-boxow z pierwszego przebiegu (Gemini nie zwraca ich w obecnym schemacie
JSON), wiec fizyczny crop nie jest mozliwy bez zmiany prompta/schematu glownego przebiegu (za
duze ryzyko dla juz dostrojonego prompta - swiadomie odlozone). Model i tak potrafi namierzyc
wlasciwy wiersz po nazwie materialu, ktora jest silnym, jednoznacznym punktem odniesienia.

Best-effort: kazdy blad (siec, niepoprawny JSON, brak klucza) konczy sie cichym (None, None) -
to dodatkowa siatka bezpieczenstwa, nie krytyczna sciezka przetwarzania calego dokumentu."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from .chain import run_ocr_chain
from .parsing import extract_json, parse_float_loose

_VERIFY_PROMPT_TEMPLATE = (
    'Jesteś przemysłowym silnikiem OCR do dokumentów magazynowych. Na obrazie znajdź WYŁĄCZNIE '
    'wiersz z nazwą materiału dokładnie: "{nazwa}". Jeśli nie znajdziesz dokładnie takiego '
    'wiersza, zwróć {{"ilosc_wydana":null,"ilosc_zuzyta":null}}.\n\n'
    'W tym JEDNYM wierszu odczytaj OSOBNO dwie kolumny: "Ilość wydana" i "Ilość zużyta". '
    'Ptaszek/haczyk/V/✓ to NIE jest liczba. Ptaszek i cyfra ilości moga wystepowac RAZEM w tej '
    'samej komorce jako dwa osobne znaki - jesli obok ptaszka widac takze odrebna, wyrazna cyfre '
    '(nawet "1"), odczytaj ja normalnie, nie ignoruj jej. Jesli w komorce jest WYLACZNIE sam '
    'ptaszek bez zadnego dodatkowego sladu cyfry - zwroc null dla tej kolumny.\n\n'
    'Zwróć WYŁĄCZNIE obiekt JSON (bez markdown, bez komentarzy): '
    '{{"ilosc_wydana": <liczba lub null>, "ilosc_zuzyta": <liczba lub null>}}'
)


@dataclass
class VerifyResult:
    ilosc_wydana: Optional[float]
    ilosc_zuzyta: Optional[float]

    @property
    def found_anything(self) -> bool:
        return self.ilosc_wydana is not None or self.ilosc_zuzyta is not None


async def verify_ambiguous_quantity(
    files: list[tuple[bytes, str]], nazwa: str,
    log_context: Optional[Mapping[str, object]] = None,
) -> VerifyResult:
    prompt = _VERIFY_PROMPT_TEMPLATE.format(nazwa=nazwa.replace('"', "'"))
    try:
        chain_result = await run_ocr_chain(
            files, prompt,
            log_context={**dict(log_context or {}), "ai_stage": "quantity_verification"},
        )
    except Exception:
        return VerifyResult(None, None)

    parsed = extract_json(chain_result.text)
    if not isinstance(parsed, dict):
        return VerifyResult(None, None)

    wydana = parsed.get("ilosc_wydana")
    zuzyta = parsed.get("ilosc_zuzyta")
    return VerifyResult(
        ilosc_wydana=parse_float_loose(wydana) if wydana not in (None, "") else None,
        ilosc_zuzyta=parse_float_loose(zuzyta) if zuzyta not in (None, "") else None,
    )
