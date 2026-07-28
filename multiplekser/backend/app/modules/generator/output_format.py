"""getFilename()/encodeCP1250() - port 1:1 z monolitu. Kodowanie CP1250 (Windows-1250) uzywane
przez Comarch Optima przy imporcie pliku TXT (patrz downloadOutput() w monolicie)."""
from __future__ import annotations

import re

_FILENAME_SANITIZE_RE = re.compile(r'[\\/:*?"<>|]+')

_CP1250_MAP: dict[str, int] = {
    "Ą": 0xA5, "ą": 0xB9, "Ć": 0xC6, "ć": 0xE6, "Ę": 0xCA, "ę": 0xEA,
    "Ł": 0xA3, "ł": 0xB3, "Ń": 0xD1, "ń": 0xF1, "Ó": 0xD3, "ó": 0xF3,
    "Ś": 0x8C, "ś": 0x9C, "Ź": 0x8F, "ź": 0x9F, "Ż": 0xAF, "ż": 0xBF,
}


def get_filename(numer_projektu: str | None) -> str:
    p = (numer_projektu or "").strip()
    if not p:
        p = "receptura"
    p = _FILENAME_SANITIZE_RE.sub("-", p)
    return p + ".txt"


def format_qty(value: float) -> str:
    """Formatuje ilosc tak jak JS String(number) - bez zbednego '.0' dla liczb calkowitych
    (Optima TXT to prosty format tekstowy, nie powinien dostawac '5.0' zamiast '5')."""
    if value == int(value):
        return str(int(value))
    return f"{value:.10g}"


def encode_cp1250(text: str) -> bytes:
    """Nieznane (spoza ASCII i spoza mapy powyzej) znaki -> '?' (0x3F), tak jak w monolicie -
    format docelowy (Optima) obsluguje tylko polskie znaki z tej konkretnej mapy."""
    out = bytearray(len(text))
    for i, ch in enumerate(text):
        code = ord(ch)
        out[i] = code if code < 128 else _CP1250_MAP.get(ch, 0x3F)
    return bytes(out)
