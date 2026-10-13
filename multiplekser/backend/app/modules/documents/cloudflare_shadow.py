"""Reczny benchmark Cloudflare Gemma 4 Vision w trybie shadow.

Bez zmiany receptur, pozycji, matcherow, statusow lub eksportow TXT.
Korzysta z tej samej strony i schematu OCR co produkcja. Nie uruchamia sie automatycznie.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.matcher import rules_from_db
from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.pipeline_elektryka import recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import CloudflareProvider
from app.modules.products import Catalog
from . import repository
from .background_verification import _background_review_item
from .groq_shadow import _compare_shadow, _summary_reason
from .ocr_processing import _download_and_prepare

logger = logging.getLogger(__name__)

# Ten prompt skrocony przeszedl rzeczywisty test Hydrauliki: 9 pozycji w 21.6 s.
# Gemini nadal ma niezmieniony, pelny prompt i jest produkcyjnym OCR.
_CLOUDFLARE_PROMPT = (
    'Dokladny OCR polskiej wydawki materialowej. Odczytaj TYLKO pozycje z widocznym '
    'oznaczeniem ilosci w jednej z dwoch kolumn. Puste drukowane wiersze pomin. '
    'Ilosc wydana i zuzyta sa niezalezne; nie kopiuj wartosci. '
    'Ptaszek V/X obok cyfry nie jest liczba, ale cyfra 1 obok ptaszka jest prawdziwa. '
    'Nie przesuwaj liczb ani nazw miedzy sasiednimi wierszami. '
    'Skreslone wartosci zastap poprawka, zachowaj reczne dopiski poza tabela. '
    'Nieczytelne ilosci=null; nie zgaduj. '
    'Dla kazdej pozycji zwroc: kod, nazwa, jm, ilosc_wydana, ilosc_zuzyta, '
    'uwagi, ma_oznaczenie (true), ilosc_wydana_raw, ilosc_zuzyta_raw, confidence. '
    'Z naglowka odczytaj numer_projektu, pracownik, numer_plomby (null jesli nieczytelne). '
    'ZWROC TYLKO JSON: {"numer_projektu":null,"pracownik":null,"numer_plomby":null,'
    '"pozycje":[{"kod":"","nazwa":"Bateria umywalkowa","jm":"szt",'
    '"ilosc_wydana":1,"ilosc_zuzyta":null,"ma_oznaczenie":true,'
    '"ilosc_wydana_raw":"1","ilosc_zuzyta_raw":null,"uwagi":"","confidence":99}]}'
)


class CloudflareShadowProvider(CloudflareProvider):
    async def recognize(self, *, files, model, api_key, prompt, thinking_level="low") -> str:
        return await super().recognize(
            files=files, model=model, api_key=api_key,
            prompt=_CLOUDFLARE_PROMPT, thinking_level=thinking_level,
        )


def run_cloudflare_shadow_task(document_id: str, session: Session) -> None:
    if (not settings.cloudflare_shadow_enabled
            or not settings.cloudflare_api_token or not settings.cloudflare_account_id):
        return
    doc = repository.get_document(session, document_id)
    if doc is None or doc.status != "done" or doc.dzial not in {"elektryka", "hydraulika"}:
        return
    from .storage import get_storage
    started = time.perf_counter()
    try:
        files = list(_download_and_prepare(get_storage, doc.file_key, doc.mime))
        for extra in doc.extra_files:
            files.extend(_download_and_prepare(get_storage, extra.file_key, extra.mime))
        if not files or len(files) > 3:
            repository.append_ai_trace_event(session, doc, {
                "status": "skipped", "stage": "cloudflare_shadow", "provider": "Cloudflare",
                "model": settings.cloudflare_model, "label": "Cloudflare Gemma 4 shadow",
                "reason": f"Limit bezpiecznego testu: wymagane 1-3 strony, jest {len(files)}",
                "duration_ms": 0, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            return

        catalog = Catalog.from_db(session, dzial=doc.dzial)
        chain = [OCRChainStep(
            "Cloudflare Gemma 4 shadow", CloudflareShadowProvider(),
            settings.cloudflare_model, settings.cloudflare_api_token, 120,
        )]
        results = []
        for index, file in enumerate(files, start=1):
            if doc.dzial == "hydraulika":
                result = asyncio.run(recognize_document_hydraulika(
                    [file], catalog, magazyn=doc.magazyn, chain=chain,
                    log_context={"document_id": document_id, "cloudflare_shadow": True},
                    event_callback=None, cooldown_store=None,
                ))
            else:
                result = asyncio.run(recognize_document(
                    [file], catalog, rules_from_db(session), magazyn=doc.magazyn, chain=chain,
                    log_context={"document_id": document_id, "cloudflare_shadow": True},
                    event_callback=None, cooldown_store=None,
                ))
            results.extend(result.pozycje)
            logger.info("Cloudflare shadow strona %s/%s: %s pozycji",
                        index, len(files), len(result.pozycje))

        main_items = []
        for item in doc.items:
            row = _background_review_item(item)
            if row is not None:
                main_items.append(row)
        metrics = _compare_shadow(main_items, results)
        duration_ms = round((time.perf_counter() - started) * 1000)
        repository.append_ai_trace_event(session, doc, {
            "status": "completed", "stage": "cloudflare_shadow",
            "provider": "Cloudflare", "model": settings.cloudflare_model,
            "label": "Cloudflare Gemma 4 shadow",
            "reason": f"Gemma {len(files)} stron; " + (
                _summary_reason(metrics, len(results), len(main_items))
                .replace("Groq shadow:", "Cloudflare shadow:")
                .replace("qwen=", "gemma=")
                .replace("tylko qwen=", "tylko gemma=")
                .replace("qwen-only:", "gemma-only:")
            ),
            "duration_ms": duration_ms,
            "target": f"matched={metrics['matched']};exact_qty={metrics['exact_qty']}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Cloudflare shadow zakonczony: %s", metrics)
    except Exception as exc:
        session.rollback()
        logger.warning("Cloudflare shadow nieudany", exc_info=True)
        repository.append_ai_trace_event(session, doc, {
            "status": "failed", "stage": "cloudflare_shadow", "provider": "Cloudflare",
            "model": settings.cloudflare_model, "label": "Cloudflare Gemma 4 shadow",
            "reason": str(exc)[:400],
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
