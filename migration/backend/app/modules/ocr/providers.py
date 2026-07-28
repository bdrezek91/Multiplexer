"""Strategy dla dostawcow OCR - wzorzec z docs/ETAP_0_analiza_architektury.md (diagram klas
OCRProvider). Dodanie nowego dostawcy = nowa klasa implementujaca recognize(), zero zmian gdzie
indziej. W tym etapie przeniesiony jest tylko Gemini - jedyny faktycznie uzyty w AI_CHAIN
monolitu (NVIDIA/OpenRouter byly tam gotowymi szkieletami, nigdy nie wpietymi do lancucha).
"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from urllib.parse import quote

import httpx

from app.core.config import settings


class OCRProviderError(Exception):
    """Blad pojedynczego dostawcy - w lancuchu (chain.py) kazdy taki blad przelacza na kolejnego."""


class OCRProvider(ABC):
    @abstractmethod
    async def recognize(self, *, file_bytes: bytes, mime: str, model: str, api_key: str, prompt: str) -> str:
        """Zwraca surowy tekst odpowiedzi modelu (do sparsowania przez ocr/parsing.py)."""


class GeminiProvider(OCRProvider):
    """Port geminiRecognize() z monolitu - PDF wysylany natywnie, obrazy jako inline_data."""

    async def recognize(self, *, file_bytes: bytes, mime: str, model: str, api_key: str, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
        body = {
            "contents": [{"parts": [
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(file_bytes).decode("ascii")}},
                {"text": prompt},
            ]}],
            # thinkingLevel "low" wylacza gleboke rozumowanie - przy odczycie tabeli zbedne,
            # a skraca czas odpowiedzi nawet kilkukrotnie (komentarz z monolitu).
            "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingLevel": "low"}},
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
                resp = await client.post(url, params={"key": api_key}, json=body)
        except httpx.TimeoutException as exc:
            raise OCRProviderError(f"Timeout po {settings.ocr_timeout_seconds} s bez odpowiedzi") from exc
        except httpx.HTTPError as exc:
            raise OCRProviderError(f"Błąd połączenia: {exc}") from exc

        if resp.status_code >= 400:
            raise OCRProviderError(f"API {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        candidates = data.get("candidates") or []
        cand = candidates[0] if candidates else {}
        parts = (cand.get("content") or {}).get("parts") or []
        return "\n".join(p.get("text") or "" for p in parts)
