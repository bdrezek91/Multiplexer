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
    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "medium",
    ) -> str:
        """Zwraca surowy tekst odpowiedzi modelu (do sparsowania przez ocr/parsing.py).
        `files` to lista (bytes, mime) - zwykle jeden element, ale wiecej niz jeden gdy
        dokument sklada sie z kilku osobnych plikow (np. dwa zdjecia z telefonu = dwie strony
        tej samej papierowej wydawki, patrz historia czatu). `thinking_level` - patrz
        GeminiProvider nizej (ignorowane przez dostawcow bez tej koncepcji, np. OpenAI)."""


class GeminiProvider(OCRProvider):
    """Port geminiRecognize() z monolitu - PDF wysylany natywnie, obrazy jako inline_data.
    Wiele plikow trafia jako wiele czesci `inline_data` w JEDNYM zapytaniu (Gemini wspiera to
    natywnie) - prompt (patrz prompt.py) instruuje model, ze wtedy to kolejne strony jednego
    dokumentu, nie osobne dokumenty."""

    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "medium",
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
        file_parts = [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(file_bytes).decode("ascii")}}
            for file_bytes, mime in files
        ]
        body = {
            "contents": [{"parts": [*file_parts, {"text": prompt}]}],
            # thinkingLevel domyslnie "medium" (2026-08-04, realny przypadek produkcyjny) - przy
            # formularzach z grupami niemal identycznych wierszy pod rzad (np. "Rozdzielnica SRN
            # 12/24/36/48") model przy "low" potrafil "zgubic wiersz" i zmyslic zaznaczenie na
            # sasiedniej etykiecie mimo temperature=0. Wywolujacy moze jednak zazadac "low" dla
            # prostszych zadan (patrz classify.py - klasyfikacja dzialu to trywialna decyzja, nie
            # potrzebuje glebszego rozumowania, a spowalniala CALY dokument, bo jest pierwszym z
            # dwoch sekwencyjnych zapytan) - poprawnosc pozostaje priorytetem tam, gdzie faktycznie
            # ma znaczenie (pelny odczyt tabeli), nie wszedzie na sile.
            "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingLevel": thinking_level}},
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


class OpenAIProvider(OCRProvider):
    """Ostatni krok w default_ocr_chain() (patrz chain.py) - uzywany WYLACZNIE gdy wszystkie
    kroki Gemini zawioda. Responses API (nie starsze Chat Completions) - obsluguje natywnie
    zarowno obrazy (input_image) jak i PDF (input_file) w jednym zapytaniu, tak samo jak Gemini
    w GeminiProvider powyzej."""

    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "medium",
    ) -> str:
        # thinking_level ignorowane - Responses API dla gpt-4o nie ma tego pojecia (parametr
        # istnieje tylko dla zgodnosci z interfejsem OCRProvider, patrz klasa bazowa wyzej).
        url = "https://api.openai.com/v1/responses"
        content_parts = []
        for file_bytes, mime in files:
            b64 = base64.b64encode(file_bytes).decode("ascii")
            if mime == "application/pdf":
                content_parts.append({
                    "type": "input_file", "filename": "dokument.pdf",
                    "file_data": f"data:{mime};base64,{b64}",
                })
            else:
                content_parts.append({"type": "input_image", "image_url": f"data:{mime};base64,{b64}"})
        content_parts.append({"type": "input_text", "text": prompt})

        body = {"model": model, "input": [{"role": "user", "content": content_parts}], "temperature": 0}
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
                resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise OCRProviderError(f"Timeout po {settings.ocr_timeout_seconds} s bez odpowiedzi") from exc
        except httpx.HTTPError as exc:
            raise OCRProviderError(f"Błąd połączenia: {exc}") from exc

        if resp.status_code >= 400:
            raise OCRProviderError(f"API {resp.status_code}: {resp.text[:300]}")

        data = resp.json()
        texts = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    texts.append(part.get("text") or "")
        return "\n".join(texts)
