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
    _prepare_distinct_sources,
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
        if document.extra_files:
            # Same multi-page PDF added as both file 1 and file 2 must not be
            # sent twice to OCR (would double every item and exported quantity).
            source_files = [(document.file_key, document.mime)] + [
                (extra.file_key, extra.mime) for extra in document.extra_files
            ]
            files, duplicated_uploads = _prepare_distinct_sources(get_storage, source_files)
            if duplicated_uploads:
                save_ai_event({
                    "status": "skipped", "stage": "duplicate_upload",
                    "provider": None, "model": None,
                    "label": "Pominięto identyczny załącznik",
                    "reason": f"Pominięto {duplicated_uploads} identycznych plików przed OCR.",
                    "step": None, "total_steps": None,
                    "duration_ms": 0, "attempt": 1, "target": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
        else:
            files = list(_download_and_prepare(get_storage, document.file_key, document.mime))
        timings["timing_file_prepare"] = _elapsed_ms(stage_started)

        # AUTO: exclusively the two FREE Gemini projects, never Claude or PAID.
        # Failure stops the document safely; user can retry when quotas recover.
        auto_mode = document.source_type == "auto_v3"
        if auto_mode:
            from .auto_v3 import recognize_gemini_primary
            started_gemini = time.perf_counter()
            try:
                classify_result, dzial, result, gemini_timings = recognize_gemini_primary(
                    files, session, document.magazyn,
                    event_callback=save_ai_event, cooldown_store=cooldown_store,
                )
            except (AllProvidersFailedError, OCRProviderError, OCRUnparsableResponseError,
                    RuntimeError, TimeoutError, ValueError) as exc:
                save_ai_event({
                    "status": "failed", "stage": "auto_gemini_primary",
                    "provider": "Gemini", "model": None,
                    "label": "Gemini FREE 1 i FREE 2 niedostępne",
                    "reason": "Żaden darmowy Gemini nie oddał poprawnej wydawki. Spróbuj ponownie później.",
                    "step": None, "total_steps": None,
                    "duration_ms": _elapsed_ms(started_gemini),
                    "attempt": 1, "target": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
                raise OCRProviderError("Gemini FREE 1 i FREE 2: brak poprawnego OCR. Prześlij wydawkę ponownie później.") from exc
            timings.update(gemini_timings)
            save_ai_event({
                "status": "completed", "stage": "auto_gemini_primary",
                "provider": "Gemini", "model": result.used_provider,
                "label": "AUTO: OCR Gemini FREE 1 / FREE 2",
                "reason": f"Odczytano {len(result.pozycje)} pozycji ({dzial}); bez płatnego API.",
                "step": None, "total_steps": None,
                "duration_ms": _elapsed_ms(started_gemini),
                "attempt": 1, "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        else:
            # Backwards compatibility with older already-queued standard documents.
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
        asyncio.run(_verify_ambiguous_items(
            files, items, document_id, save_ai_event, cooldown_store, dzial,
        ))
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
        # Safety invariant: JEV maps product codes; it must NEVER change OCR quantities.
        qty_before_jev = [(item.get("ilosc_wydana"), item.get("ilosc_zuzyta"))
                          for item in items]
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

        if dzial == "hydraulika":
            from app.modules.generator.safety_hydraulika import (
                is_ignored_zas127, screw_code_safe,
            )
            for item in items:
                name = item.get("rozpoznana_nazwa")
                if is_ignored_zas127(name):
                    item["match_kod"] = None
                    item["match_nazwa"] = None
                    item["matched_product_id"] = None
                    item["match_quality"] = "excluded"
                    item["needs_review"] = False
                    item["form_note"] = (item.get("form_note") or "") + " ZAS 127: celowo pominięte w TXT."
                elif not screw_code_safe(
                    name, item.get("match_kod"), item.get("match_nazwa")
                ):
                    item["match_kod"] = None
                    item["match_nazwa"] = None
                    item["matched_product_id"] = None
                    item["match_quality"] = "bad"
                    item["needs_review"] = True
                    item["form_note"] = (item.get("form_note") or "") + (
                        " Wkręty: zablokowano niezgodny kod (rozmiar lub RAL)."
                    )


        # Never let matcher/JEV overwrite the original quantities, regardless
        # of which FREE Gemini project produced them.
        for index, item in enumerate(items):
            before = qty_before_jev[index]
            if (item.get("ilosc_wydana"), item.get("ilosc_zuzyta")) != before:
                item["ilosc_wydana"], item["ilosc_zuzyta"] = before
                item["needs_review"] = True
                item["form_note"] = (item.get("form_note") or "") + (
                    " JEV: nieautoryzowana zmiana ilości — przywrócono odczyt OCR."
                )

        stage_started = time.perf_counter()
        repository.mark_done(
            session, document,
            numer_projektu=result.numer_projektu, used_provider=result.used_provider,
            rejected_count=result.rejected_count, items=items,
            dzial=dzial, dzial_confidence=classify_result.confidence,
            pracownik=result.pracownik,
            numer_plomby=None if dzial == "hydraulika" else result.numer_plomby,
        )
        timings["timing_finalize_db"] = _elapsed_ms(stage_started)
        timings["timing_to_done"] = _elapsed_ms(task_started)

        timing_events = [_timing_event(stage, duration) for stage, duration in timings.items()]
        if not auto_mode:
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
            if not auto_mode:
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
                and completed.source_type != "auto_v3"):
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
