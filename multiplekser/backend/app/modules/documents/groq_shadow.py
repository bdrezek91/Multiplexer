"""Niezalezny shadow OCR Groq/Qwen.

Task dziala po status=done na kolejce background. Nigdy nie modyfikuje pozycji dokumentu,
matchera, ilosci, statusu ani statystyk. Zapisuje tylko jeden skondensowany event do ai_trace.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.matcher import rules_from_db
from app.modules.ocr.chain import OCRChainStep
from app.modules.ocr.pipeline_elektryka import recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.ocr.providers import GroqProvider
from app.modules.products import Catalog
from app.modules.products.catalog import plain_norm

from . import repository
from .background_verification import _background_review_item
from .ocr_processing import _download_and_prepare

logger = logging.getLogger(__name__)

def _qty_pair(obj) -> tuple[float | None, float | None]:
    return (
        float(obj.ilosc_wydana) if obj.ilosc_wydana is not None else None,
        float(obj.ilosc_zuzyta) if obj.ilosc_zuzyta is not None else None,
    )


def _compare_shadow(main_items: list[dict], shadow_items) -> dict[str, object]:
    """Porownuje tylko identycznie znormalizowane etykiety, bez fuzzy zgadywania."""
    shadow_rows = [
        {
            "name": it.rozpoznana_nazwa,
            "norm": plain_norm(it.rozpoznana_nazwa),
            "qty": _qty_pair(it),
            "used": False,
        }
        for it in shadow_items
    ]
    matched = 0
    exact_qty = 0
    mismatches: list[str] = []
    main_only: list[str] = []

    for main in main_items:
        norm = plain_norm(str(main["rozpoznana_nazwa"]))
        row = next((r for r in shadow_rows if not r["used"] and r["norm"] == norm), None)
        if row is None:
            main_only.append(str(main["rozpoznana_nazwa"]))
            continue
        row["used"] = True
        matched += 1
        main_qty = (
            float(main["ilosc_wydana"]) if main["ilosc_wydana"] is not None else None,
            float(main["ilosc_zuzyta"]) if main["ilosc_zuzyta"] is not None else None,
        )
        if row["qty"] == main_qty:
            exact_qty += 1
        elif len(mismatches) < 6:
            mismatches.append(
                f'{main["rozpoznana_nazwa"]}: {main_qty[0]}/{main_qty[1]} -> '
                f'{row["qty"][0]}/{row["qty"][1]}'
            )

    shadow_only = [
        str(r["name"]) for r in shadow_rows if not r["used"] and r["qty"] != (None, None)
    ]
    return {
        "matched": matched,
        "exact_qty": exact_qty,
        "mismatch_count": max(0, matched - exact_qty),
        "main_only_count": len(main_only),
        "shadow_only_count": len(shadow_only),
        "mismatches": mismatches,
        "main_only": main_only[:4],
        "shadow_only": shadow_only[:4],
    }


def _summary_reason(metrics: dict[str, object], shadow_count: int, main_count: int) -> str:
    parts = [
        f"Groq shadow: pozycje main={main_count}, qwen={shadow_count}",
        f"etykiety wspolne={metrics['matched']}",
        f"ilosci identyczne={metrics['exact_qty']}",
        f"rozne ilosci={metrics['mismatch_count']}",
        f"tylko main={metrics['main_only_count']}",
        f"tylko qwen={metrics['shadow_only_count']}",
    ]
    details = []
    if metrics["mismatches"]:
        details.append("roznice: " + "; ".join(metrics["mismatches"]))
    if metrics["main_only"]:
        details.append("main-only: " + ", ".join(metrics["main_only"]))
    if metrics["shadow_only"]:
        details.append("qwen-only: " + ", ".join(metrics["shadow_only"]))
    if details:
        parts.append(" | ".join(details))
    return " | ".join(parts)[:1800]


def run_groq_shadow_task(
    document_id: str, session: Session, *, page_index: int = 0,
    accumulated: list[dict] | None = None, duration_ms_total: int = 0,
) -> None:
    if not settings.groq_shadow_enabled or not settings.groq_api_key:
        return

    document = repository.get_document(session, document_id)
    if (
        document is None
        or document.status != "done"
        or document.dzial not in {"elektryka", "hydraulika"}
    ):
        return

    # Jedna strona z pelnym promptem to ~6k tokenow; limit konta to 7k ITPM.
    # Rezerwacja Redis obejmuje wszystkie dokumenty. Zajety slot odracza zadanie
    # w Celery zamiast blokowac worker-background na 70+ sekund.
    from .tasks import process_groq_shadow
    throttle = Redis.from_url(settings.redis_url)
    try:
        reserved = throttle.set("multiplekser:groq:itpm_slot", "1", nx=True, ex=75)
        retry_after = max(3, throttle.ttl("multiplekser:groq:itpm_slot") + 2) if not reserved else 0
    finally:
        throttle.close()
    if retry_after:
        process_groq_shadow.apply_async(
            kwargs={"document_id": document_id, "page_index": page_index,
                    "accumulated": accumulated, "duration_ms_total": duration_ms_total},
            countdown=retry_after, queue="background",
        )
        return

    from .storage import get_storage

    started = time.perf_counter()
    try:
        files = list(_download_and_prepare(get_storage, document.file_key, document.mime))
        for extra in document.extra_files:
            files += _download_and_prepare(get_storage, extra.file_key, extra.mime)

        if not files or not (0 <= page_index < len(files)):
            raise ValueError(f"Nieprawidlowy indeks strony {page_index} / {len(files)}")
        one_page = [files[page_index]]

        chain = [OCRChainStep(
            "Groq Qwen 3.8 27B shadow",
            GroqProvider(),
            settings.groq_model,
            settings.groq_api_key,
            45,
        )]
        catalog = Catalog.from_db(session, dzial=document.dzial)
        if document.dzial == "hydraulika":
            result = asyncio.run(recognize_document_hydraulika(
                one_page,
                catalog,
                magazyn=document.magazyn,
                chain=chain,
                log_context={"document_id": document_id, "groq_shadow": True},
                event_callback=None,
                cooldown_store=None,
            ))
        else:
            result = asyncio.run(recognize_document(
                one_page,
                catalog,
                rules_from_db(session),
                magazyn=document.magazyn,
                chain=chain,
                log_context={"document_id": document_id, "groq_shadow": True},
                event_callback=None,
                cooldown_store=None,
            ))

        current_rows = [
            {"rozpoznana_nazwa": item.rozpoznana_nazwa,
             "ilosc_wydana": float(item.ilosc_wydana) if item.ilosc_wydana is not None else None,
             "ilosc_zuzyta": float(item.ilosc_zuzyta) if item.ilosc_zuzyta is not None else None}
            for item in result.pozycje
        ]
        all_rows = list(accumulated or []) + current_rows
        total_duration = duration_ms_total + round((time.perf_counter() - started) * 1000)
        if page_index + 1 < len(files):
            process_groq_shadow.apply_async(
                kwargs={"document_id": document_id, "page_index": page_index + 1,
                        "accumulated": all_rows, "duration_ms_total": total_duration},
                countdown=3, queue="background",
            )
            logger.info("Groq shadow strona %s/%s: %s pozycji, nastepna odroczona",
                        page_index + 1, len(files), len(current_rows))
            return
        combined_items = [SimpleNamespace(**row) for row in all_rows]

        main_items = []
        for row in document.items:
            review = _background_review_item(row)
            if review is not None:
                main_items.append(review)

        metrics = _compare_shadow(main_items, combined_items)
        duration_ms = total_duration
        repository.append_ai_trace_event(session, document, {
            "status": "completed",
            "stage": "groq_shadow",
            "provider": "Groq",
            "model": settings.groq_model,
            "label": "Groq Qwen 3.8 27B shadow",
            "reason": f"Qwen OCR {len(files)} stron; " + _summary_reason(metrics, len(combined_items), len(main_items)),
            "step": None,
            "total_steps": None,
            "duration_ms": duration_ms,
            "attempt": 1,
            "target": f"matched={metrics['matched']};exact_qty={metrics['exact_qty']}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(
            "Groq shadow zakonczony",
            extra={"document_id": document_id, "duration_ms": duration_ms, **metrics},
        )
    except Exception as exc:
        session.rollback()
        logger.warning("Groq shadow nieudany", exc_info=True, extra={"document_id": document_id})
        try:
            repository.append_ai_trace_event(session, document, {
                "status": "failed",
                "stage": "groq_shadow",
                "provider": "Groq",
                "model": settings.groq_model,
                "label": "Groq Qwen 3.8 27B shadow",
                "reason": str(exc)[:500],
                "step": None,
                "total_steps": None,
                "duration_ms": round((time.perf_counter() - started) * 1000),
                "attempt": 1,
                "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            session.rollback()
