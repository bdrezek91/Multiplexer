"""AUTO V4 experimental one-pass Gemini OCR. SHADOW ONLY; never persists document items.

The production AUTO V3 path remains the authority until independently approved.
"""
from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.modules.ocr.parsing import extract_json, validate_item, is_actionable_item
from .auto_v3 import classify_auto_dzial, AmbiguousDepartment

# Deliberately preserve the hard-earned production OCR safety rules.
V4_PROMPT = """Jesteś wyłącznie przemysłowym OCR wydawki magazynowej Elektryka/Hydraulika.
ODCZYT LITERALNY ze WSZYSTKICH dostarczonych stron jednego dokumentu. Nie wybieraj kodów,
produktów ani magazynu. Odczytaj z pierwszego nagłówka dział (Elektryka lub Hydraulika),
numer projektu i pracownika. Przeczytaj wszystkie wiersze tabeli i dopiski poza tabelą,
również pod INNE. Zwróć tylko pozycje, w których JEST ręczna ilość lub niejednoznaczny
ręczny zapis mogący oznaczać ilość. Puste wydrukowane wiersze pomiń.

W wydawce są DWIE OSOBNE kolumny: ILOŚĆ WYDANA i ILOŚĆ ZUŻYTA.
Nigdy nie przepisuj ilości między kolumnami ani między sąsiadującymi wierszami.
Cyfra 1 (czasem ukośna kreska /) może występować OBOK czarnego ptaszka V/✓.
Ptaszek sam NIE oznacza liczby 1. Zapis typu '-' oznacza pusto, nie 1.
Nie myl 1 z 4 lub 7, 7 z poprzeczką z 2, 9 z 7.
Skreślona wartość nie obowiązuje: wybierz tylko ręcznie poprawioną obok.
Jeśli kolumna jest nieczytelna, oddaj null, nie zgaduj wartości.
Zachowaj nazwy dosłownie, nie rozwijaj nieczytelnych skrótów i nie mieszaj podobnych
wierszy, wymiarów ani kolorów. Nie dodawaj pozycji na podstawie samej etykiety INNE,
nawet gdy blisko niej jest liczba. W niepewnych wierszach ustaw ma_oznaczenie=true,
ale nie wymyślaj ilości. Numer strony zachowaj do wykrywania pominięć.
W szczególności w Hydraulice nie uznawaj śruby 8 mm i zaślepki 127 za automatyczne
pozycje do wydania — decyzję o wyłączeniu pozostaw regułom systemu.
Zwróć wyłącznie JSON według schematu, wszystkie strony w jednej liście w kolejności.
"""

_NULL_NUMBER = {"type": ["number", "null"]}
_NULL_STRING = {"type": ["string", "null"]}
V4_SCHEMA: dict[str, Any] = {
    "type": "object", "properties": {
        "dzial": {"type": "string", "enum": ["elektryka", "hydraulika"]},
        "numer_projektu": _NULL_STRING,
        "pracownik": _NULL_STRING,
        "pozycje": {"type": "array", "items": {"type": "object", "properties": {
            "nazwa": {"type": "string"},
            "ilosc_wydana": _NULL_NUMBER,
            "ilosc_zuzyta": _NULL_NUMBER,
            "ilosc_wydana_raw": _NULL_STRING,
            "ilosc_zuzyta_raw": _NULL_STRING,
            "ma_oznaczenie": {"type": "boolean"},
            "strona": {"type": "integer"},
        }, "required": ["nazwa", "ilosc_wydana", "ilosc_zuzyta", "ilosc_wydana_raw", "ilosc_zuzyta_raw", "ma_oznaczenie", "strona"]}},
    }, "required": ["dzial", "numer_projektu", "pracownik", "pozycje"],
}

@dataclass(frozen=True)
class V4ShadowResult:
    model: str
    thinking: str
    seconds: float
    dzial: str
    rows: list[dict]
    source_count: int
    invalid_count: int
    usage: dict[str, Any]


async def shadow_one_pass(
    files: list[tuple[bytes, str]], *, model: str = "gemini-3.5-flash-lite",
    thinking: str = "minimal", timeout_seconds: float = 23,
    api_key: str | None = None,
) -> V4ShadowResult:
    """Call Google once; NEVER write the results to production documents."""
    if not files or len(files) > 8:
        raise ValueError("V4 only supports 1-8 pages")
    if model not in {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"}:
        raise ValueError("V4 model not allowlisted")
    if thinking not in ({"minimal", "low"} if model != "gemini-3.8-flash" else {"low"}):
        raise ValueError("Invalid thinking level")
    key = api_key or settings.gemini_api_key_free
    if not key:
        raise ValueError("No Gemini free API key")
    parts = [{"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode("ascii")}}
             for data, mime in files]
    parts.append({"text": V4_PROMPT})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "thinkingConfig": {"thinkingLevel": thinking},
            "responseMimeType": "application/json",
            "responseJsonSchema": V4_SCHEMA,
            "temperature": 1,
        },
    }
    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
        res = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            json=body, headers={"x-goog-api-key": key},
        )
    if not res.is_success:
        try:
            error = res.json().get("error", {})
            status = error.get("status", "UNKNOWN")
            message = str(error.get("message", ""))[:180].replace("\n", " ")
        except ValueError:
            status, message = "BAD_RESPONSE", ""
        raise RuntimeError(f"Gemini V4 HTTP {res.status_code} {status}: {message}")
    payload = res.json()
    txt = "".join(p.get("text", "") for c in payload.get("candidates", [])
                  for p in (c.get("content") or {}).get("parts", []))
    parsed = extract_json(txt)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("pozycje"), list):
        raise ValueError("Gemini V4 returned invalid JSON data")
    raw_rows = parsed["pozycje"]
    valid_rows = [r for r in raw_rows if validate_item(r) and is_actionable_item(r)]
    invalid = len(raw_rows) - len(valid_rows)
    # IMPORTANT: the model's own category is NOT independent evidence.
    # Derive department purely from recognized material names, and stop if unknown.
    local_evidence = [{"nazwa": r["nazwa"]} for r in valid_rows]
    dzial, _, _ = classify_auto_dzial(local_evidence)
    if dzial != parsed.get("dzial") or not valid_rows:
        raise AmbiguousDepartment("V4 department or material list is unsafe")
    return V4ShadowResult(model=model, thinking=thinking,
                          seconds=round(time.perf_counter()-start, 3),
                          dzial=dzial, rows=valid_rows,
                          source_count=len(raw_rows), invalid_count=invalid,
                          usage=payload.get("usageMetadata") or {})
