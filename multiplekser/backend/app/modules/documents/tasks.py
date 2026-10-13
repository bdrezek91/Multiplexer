"""Taski Celery dla dokumentow.

Ten modul jest celowo cienkim orkiestratorem. Szczegoly OCR/postprocessingu sa w
ocr_processing.py, druga kontrola w background_verification.py, a telemetryka w task_telemetry.py.
Nazwy pomocnicze sa re-exportowane ponizej dla zgodnosci wstecznej z testami i istniejacym kodem.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.matcher import rules_from_db
from app.modules.ocr.chain import AllProvidersFailedError
from app.modules.ocr.cooldown import get_ocr_cooldown_store
from app.modules.ocr.pipeline_elektryka import OCRUnparsableResponseError
from app.modules.ocr.providers import OCRProviderError
from app.modules.ocr.verify import verify_ambiguous_quantities
from app.modules.products import Catalog

from . import repository
from .background_verification import _background_review_item, run_full_document_verification_task
from .ocr_processing import (
    _append_auto_osprzet_gniazda_podwojnego_podtynkowego,
    _append_auto_zasilacz_led,
    _classify_and_recognize,
    _download_and_prepare,
    _podwoj_ilosc_gniazda_podwojnego_podtynkowego,
    _resolve_product_id,
    _row_dict_from_ocritem,
    _verify_ambiguous_items as _verify_ambiguous_items_impl,
)
from .retention import prune_documents
from .groq_shadow import run_groq_shadow_task
from .cloudflare_shadow import run_cloudflare_shadow_task
from .task_telemetry import (
    _background_queue_wait_ms,
    _elapsed_ms,
    _queue_wait_ms,
    _timing_event,
)

logger = logging.getLogger(__name__)


async def _verify_ambiguous_items(*args, **kwargs):
    """Kompatybilny re-export helpera po refaktorze.

    Zachowuje stary punkt monkeypatchowania verify_ambiguous_quantities w documents.tasks,
    a prawdziwa implementacja mieszka w ocr_processing.py.
    """
    return await _verify_ambiguous_items_impl(
        *args,
        _verify_func=verify_ambiguous_quantities,
        **kwargs,
    )


def run_ocr_task(document_id: str, session: Session) -> bool:
    from .storage import get_storage  # lazy import - unika inicjalizacji klienta S3 przy imporcie modulu

    # Atomowy claim chroni przed ponownym dostarczeniem tego samego zadania przez broker,
    # rownoleglym workerem i przypadkowym recznym odpaleniem tego samego document_id.
    document = repository.claim_document_for_processing(session, document_id)
    if document is None:
        logger.info(
            "OCR - dokument nie jest juz queued, pomijam duplikat",
            extra={"document_id": document_id},
        )
        return False

    task_started = time.perf_counter()
    timings: dict[str, int] = {}
    queue_wait = _queue_wait_ms(document.created_at)
    if queue_wait is not None:
        timings["timing_ocr_queue_wait"] = queue_wait

    logger.info("OCR - start przetwarzania", extra={"document_id": document_id})

    def save_ai_event(event: dict[str, object]) -> None:
        repository.append_ai_trace_event(session, document, event)

    cooldown_store = get_ocr_cooldown_store()

    try:
        # Wiele plikow = wiele osobnych stron TEGO SAMEGO dokumentu (np. dwa zdjecia z telefonu
        # jednej papierowej wydawki, ktorej nie da sie zmiescic na jednym zdjeciu, albo kolejne
        # strony wielostronicowego PDF ze skanera rozbite na obrazy - patrz _download_and_prepare
        # powyzej i historia czatu) - patrz tez ocr/providers.py. Pierwszy plik to zawsze
        # document.file_key/mime (wsteczna zgodnosc), kolejne to document.extra_files w kolejnosci
        # `sequence`. Wszystkie razem trafiaja do Gemini w jednym zapytaniu.
        stage_started = time.perf_counter()
        files = list(_download_and_prepare(get_storage, document.file_key, document.mime))
        for extra in document.extra_files:
            files += _download_and_prepare(get_storage, extra.file_key, extra.mime)
        timings["timing_file_prepare"] = _elapsed_ms(stage_started)

        # Krok Hydraulika-3: klasyfikacja dzialu PRZED pelnym odczytem (tani, pierwszy przebieg
        # Gemini - patrz ocr/classify.py) - dopiero po niej wiadomo, ktory katalog/prompt/matcher
        # uzyc. Brak recznego przelacznika w UI: uzytkownik chce w pelni automatycznego wykrywania.
        claude_test = document.source_type in {
            "claude_jev_test_elektryka", "claude_jev_test_hydraulika"
        }
        if claude_test:
            # Claude only reads images. Business logic + all catalog decisions
            # continue through the existing matcher and JEV ACTIVE below.
            from .claude_bridge import run_claude_host_bridge
            from app.modules.ocr.pipeline_elektryka import _build_item
            from app.modules.ocr.pipeline_hydraulika import _build_item_hydraulika
            from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA

            dzial = document.source_type.removeprefix("claude_jev_test_")
            raw_rows, ocr_seconds = run_claude_host_bridge(
                document_id, files, dzial,
            )
            catalog = Catalog.from_db(session, dzial=dzial)
            if dzial == "hydraulika":
                positions = [_build_item_hydraulika(row, catalog, document.magazyn)
                             for row in raw_rows]
            else:
                special_rules = rules_from_db(session)
                positions = [_build_item(row, catalog, special_rules, document.magazyn)
                             for row in raw_rows]
            for position in positions:
                if position.ilosc_wydana is None and position.ilosc_zuzyta is None:
                    position.needs_review = True
                    position.form_note = (position.form_note or "") + " Claude: nie udało się odczytać obu ilości."
            result = SimpleNamespace(
                numer_projektu=None, pracownik=None, numer_plomby=None,
                used_provider="Claude Sonnet + JEV (test)",
                rejected_count=0, pozycje=positions,
            )
            classify_result = SimpleNamespace(confidence=1.0)
            timings["timing_claude_ocr"] = int(ocr_seconds * 1000)
            save_ai_event({
                "status": "completed", "stage": "claude_test_ocr",
                "provider": "Claude", "model": "sonnet",
                "label": "Claude + JEV (test)", "reason": f"Odczytano {len(positions)} pozycji na {len(files)} stronach.",
                "step": None, "total_steps": None, "duration_ms": int(ocr_seconds * 1000),
                "attempt": 1, "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            classify_result, dzial, result, core_timings = _classify_and_recognize(
                files, session, document, save_ai_event, cooldown_store,
            )
            timings.update(core_timings)

        stage_started = time.perf_counter()
        items = [
            _row_dict_from_ocritem(
                it, it.ilosc_wydana, it.ilosc_zuzyta, session, dzial=dzial,
            )
            for it in result.pozycje
        ]
        timings["timing_item_materialization"] = _elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        if not claude_test:
            asyncio.run(_verify_ambiguous_items(
                files, items, document_id, save_ai_event, cooldown_store, dzial,
            ))
        # Claude test never calls Gemini's ambiguous-quantity checker.
        timings["timing_ambiguous_verification"] = _elapsed_ms(stage_started)

        # Najpierw zachowujemy wszystkie istniejace reguly biznesowe matchera. Auto-zasilacz
        # i mnoznik gniazda sa czescia sprawdzonej logiki i nie powinny zalezec od decyzji AI.
        stage_started = time.perf_counter()
        _append_auto_zasilacz_led(items, dzial, session)
        if dzial == "elektryka":
            _append_auto_osprzet_gniazda_podwojnego_podtynkowego(items, session)
        _podwoj_ilosc_gniazda_podwojnego_podtynkowego(items)
        timings["timing_postprocessing"] = _elapsed_ms(stage_started)

        # Jev ACTIVE: Gemini czyta dokument, obecny matcher daje bazowe dopasowanie, a Jev
        # wybiera finalny kod tylko dla Elektryki. Twarde special rules maja pierwszenstwo;
        # blad/OTHER zostawia stary matcher. Wszystkie pozycje ida do Jev rownolegle.
        active_jev_rows = []
        stage_started = time.perf_counter()
        try:
            from app.modules.decision.active import apply_jev_active
            catalog_for_jev = Catalog.from_db(session, dzial=dzial)
            # Hydraulika ma swoje stale twarde reguly (zaslepki M10, wykluczenie czerwonej).
            # Nie wysylamy elektrycznych special rules do hydrauliki.
            if dzial == "hydraulika":
                from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA
                rules_for_jev = DEFAULT_SPECIAL_RULES_HYDRAULIKA
            else:
                rules_for_jev = rules_from_db(session)
            active_jev_rows = asyncio.run(apply_jev_active(
                items=items,
                catalog=catalog_for_jev,
                special_rules=rules_for_jev,
                magazyn=document.magazyn,
                dzial=dzial,
                resolve_product_id=lambda kod: _resolve_product_id(session, kod, dzial),
            ))
        except Exception:
            logger.warning("Jev active - blad, zostawiam wyniki matchera", exc_info=True)
        finally:
            timings["timing_jev_active"] = _elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        repository.mark_done(
            session, document,
            numer_projektu=result.numer_projektu, used_provider=result.used_provider,
            rejected_count=result.rejected_count, items=items,
            dzial=dzial, dzial_confidence=classify_result.confidence,
            pracownik=result.pracownik, numer_plomby=result.numer_plomby,
        )
        timings["timing_finalize_db"] = _elapsed_ms(stage_started)
        timings["timing_to_done"] = _elapsed_ms(task_started)

        timing_events = [_timing_event(stage, duration) for stage, duration in timings.items()]
        timing_events.append({
            "status": "queued", "stage": "full_document_verification",
            "provider": None, "model": None, "label": None,
            "reason": "Główny wynik jest gotowy. Pełna kontrola dokumentu została zlecona w tle.",
            "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
            "target": None, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        repository.append_ai_trace_events(session, document, timing_events)

        if active_jev_rows:
            try:
                from app.modules.decision.tasks import persist_active_rows
                completed_document = repository.get_document(session, document.id)
                if completed_document is not None:
                    persist_active_rows(session, completed_document, active_jev_rows)
            except Exception:
                session.rollback()
                logger.warning("Jev active - nie udalo sie zapisac diagnostyki", exc_info=True)

        logger.info(
            "OCR - zakonczone sukcesem",
            extra={
                "document_id": document_id, "dzial": dzial, "used_provider": result.used_provider,
                "pozycje": len(items), "rejected_count": result.rejected_count,
            },
        )

        # Jev shadow (2026-09-29) - osobne zadanie Celery, PO zakonczeniu dokumentu, zero
        # wplywu na czas/wynik powyzej (patrz decision/tasks.py, docstring). No-op gdy
        # JEV_ENABLED=false (domyslnie, patrz docker-compose.prod.yml).
        try:
            from app.modules.decision.tasks import dispatch_jev_shadow_task
            dispatch_jev_shadow_task(document_id)
        except Exception:
            logger.warning("Jev shadow - nie udalo sie zlecic zadania, pomijam", exc_info=True)
    except (OCRUnparsableResponseError, AllProvidersFailedError, OCRProviderError) as exc:
        repository.mark_error(session, document, str(exc))
        logger.error("OCR - zakonczone bledem", extra={"document_id": document_id, "error": str(exc)})
    except Exception as exc:  # zabezpieczenie - blad nie moze zniknac w workerze bez sladu w Document.status
        repository.mark_error(session, document, f"Nieoczekiwany blad: {exc}")
        logger.exception("OCR - nieoczekiwany blad", extra={"document_id": document_id})
    finally:
        try:
            prune_documents(session, get_storage(), limit=settings.document_retention_limit)
        except Exception:
            # Awaria sprzatania nie moze zmienic wyniku poprawnie zakonczonej analizy.
            session.rollback()
            logger.exception("Retencja dokumentow nie powiodla sie")

    return True


@celery_app.task(name="documents.process_ocr")
def process_ocr_document(document_id: str) -> None:
    session = SessionLocal()
    try:
        processed = run_ocr_task(document_id, session)
        if not processed:
            return
        completed = repository.get_document(session, document_id)
        if (completed is not None and completed.status == "done"
                and not completed.source_type.startswith("claude_jev_test_")):
            try:
                dispatch_full_document_verification_task(document_id)
            except Exception:
                logger.warning(
                    "Pelna kontrola dokumentu - nie udalo sie zlecic zadania w tle",
                    exc_info=True,
                    extra={"document_id": document_id},
                )
                try:
                    repository.append_ai_trace_event(session, completed, {
                        "status": "failed", "stage": "full_document_verification",
                        "provider": None, "model": None, "label": None,
                        "reason": "Nie udało się uruchomić pełnej kontroli dokumentu w tle.",
                        "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
                        "target": None, "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    session.rollback()
            try:
                dispatch_groq_shadow_task(document_id)
            except Exception:
                logger.warning(
                    "Groq shadow - nie udalo sie zlecic zadania w tle",
                    exc_info=True,
                    extra={"document_id": document_id},
                )
    finally:
        session.close()


def dispatch_ocr_task(document_id: str) -> None:
    """Zleca przetwarzanie dokumentu do Celery. Router wywoluje WYLACZNIE ta funkcje, nigdy
    `process_ocr_document` bezposrednio - cienka warstwa oddzielajaca "co robi zadanie" od
    "jak jest zlecane"."""
    process_ocr_document.delay(document_id)


@celery_app.task(name="documents.full_document_verification")
def process_full_document_verification(document_id: str) -> None:
    session = SessionLocal()
    try:
        run_full_document_verification_task(document_id, session)
    finally:
        session.close()


def dispatch_full_document_verification_task(document_id: str) -> None:
    process_full_document_verification.delay(document_id)


@celery_app.task(name="documents.groq_shadow")
def process_groq_shadow(
    document_id: str, page_index: int = 0,
    accumulated: list[dict] | None = None, duration_ms_total: int = 0,
) -> None:
    session = SessionLocal()
    try:
        run_groq_shadow_task(
            document_id, session, page_index=page_index,
            accumulated=accumulated, duration_ms_total=duration_ms_total,
        )
    finally:
        session.close()


def dispatch_groq_shadow_task(document_id: str) -> None:
    process_groq_shadow.delay(document_id)


@celery_app.task(name="documents.cloudflare_shadow", queue="background")
def process_cloudflare_shadow(document_id: str) -> None:
    session = SessionLocal()
    try:
        run_cloudflare_shadow_task(document_id, session)
    finally:
        session.close()


def dispatch_cloudflare_shadow_task(document_id: str) -> None:
    process_cloudflare_shadow.delay(document_id)
