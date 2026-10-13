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

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class OCRProvider(ABC):
    @abstractmethod
    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "low",
    ) -> str:
        """Zwraca surowy tekst odpowiedzi modelu (do sparsowania przez ocr/parsing.py).
        `files` to lista (bytes, mime) - zwykle jeden element, ale wiecej niz jeden gdy
        dokument sklada sie z kilku osobnych plikow (np. dwa zdjecia z telefonu = dwie strony
        tej samej papierowej wydawki, patrz historia czatu). `thinking_level` - patrz
        GeminiProvider nizej (ignorowane przez dostawcow bez tej koncepcji, np. OpenAI)."""


class GeminiProvider(OCRProvider):
    """Port geminiRecognize() z monolitu - kazdy plik trafia jako `inline_data`. PDF NIE jest
    wysylany natywnie do tej klasy - jest rozbijany na osobne obrazy per strona ZANIM tu trafi
    (patrz documents/tasks.py: _download_and_prepare/ocr/image.py: pdf_to_page_images, 2026-09-09
    - natywne wysylanie calego wielostronicowego PDF bylo mniej niezawodne, model potrafil zgubic
    fragment tresci na gestym dokumencie). Wiele plikow trafia jako wiele czesci `inline_data` w
    JEDNYM zapytaniu (Gemini wspiera to natywnie) - prompt (patrz prompt.py) instruuje model, ze
    wtedy to kolejne strony jednego dokumentu, nie osobne dokumenty."""

    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "low",
    ) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent"
        file_parts = [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(file_bytes).decode("ascii")}}
            for file_bytes, mime in files
        ]
        body = {
            "contents": [{"parts": [*file_parts, {"text": prompt}]}],
            # thinkingLevel domyslnie "low" dla kazdego etapu Gemini (2026-08-05, test
            # produkcyjny pod katem skrocenia czasu pelnego OCR). Wywolujacy moze nadal jawnie
            # zazadac wyzszego poziomu dla konkretnego zadania.
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
            raise OCRProviderError(
                f"API {resp.status_code}: {resp.text[:300]}", status_code=resp.status_code,
            )

        data = resp.json()
        candidates = data.get("candidates") or []
        cand = candidates[0] if candidates else {}
        parts = (cand.get("content") or {}).get("parts") or []
        return "\n".join(p.get("text") or "" for p in parts)


class GroqProvider(OCRProvider):
    """Vision OCR przez Groq Chat Completions.

    Qwen 3.8 27B przyjmuje maksymalnie 3 obrazy w jednym zapytaniu. Multiplekser przekazuje tu
    obrazy juz przygotowane przez warstwe OCR, wiec provider nie wykonuje rasteryzacji.
    JSON mode jest wlaczony, bo oba pipeline'y OCR oczekuja obiektu JSON.
    """

    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "low",
    ) -> str:
        if not files:
            raise OCRProviderError("Brak obrazow do analizy Groq")
        if len(files) > 3:
            raise OCRProviderError(
                f"Groq {model} obsluguje maksymalnie 3 obrazy na request (otrzymano {len(files)})"
            )

        content = [{"type": "text", "text": prompt}]
        for file_bytes, mime in files:
            if not str(mime).startswith("image/"):
                raise OCRProviderError(f"Groq shadow oczekuje obrazu, otrzymano MIME {mime!r}")
            b64 = base64.b64encode(file_bytes).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })

        body = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_completion_tokens": 8192,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=settings.ocr_timeout_seconds) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise OCRProviderError(
                f"Timeout po {settings.ocr_timeout_seconds} s bez odpowiedzi Groq"
            ) from exc
        except httpx.HTTPError as exc:
            raise OCRProviderError(f"Blad polaczenia Groq: {exc}") from exc

        if resp.status_code >= 400:
            raise OCRProviderError(
                f"Groq API {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
            )

        data = resp.json()
        choices = data.get("choices") or []
        message = (choices[0].get("message") or {}) if choices else {}
        return str(message.get("content") or "")


class OpenAIProvider(OCRProvider):
    """Ostatni krok w default_ocr_chain() (patrz chain.py) - uzywany WYLACZNIE gdy wszystkie
    kroki Gemini zawioda. Responses API (nie starsze Chat Completions) - obsluguje natywnie
    zarowno obrazy (input_image) jak i PDF (input_file) w jednym zapytaniu, tak samo jak Gemini
    w GeminiProvider powyzej."""

    async def recognize(
        self, *, files: list[tuple[bytes, str]], model: str, api_key: str, prompt: str,
        thinking_level: str = "low",
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
            raise OCRProviderError(
                f"API {resp.status_code}: {resp.text[:300]}", status_code=resp.status_code,
            )

        data = resp.json()
        texts = []
        for item in data.get("output") or []:
            if item.get("type") != "message":
                continue
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    texts.append(part.get("text") or "")
        return "\n".join(texts)
