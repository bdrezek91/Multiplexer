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

        # Krok Hydraulika-3: klasyfikacja dzialu PRZED pelnym odczytem (tani, pierwszy przebieg
        # Gemini - patrz ocr/classify.py) - dopiero po niej wiadomo, ktory katalog/prompt/matcher
        # uzyc. Brak recznego przelacznika w UI: uzytkownik chce w pelni automatycznego wykrywania.
        auto_mode = document.source_type == "auto_v3"
        claude_test = document.source_type in {
            "claude_jev_test_elektryka", "claude_jev_test_hydraulika"
        }
        # AUTO now runs the established FREE Gemini form OCR first.
        # Only if Gemini is down / times out / yields unusable OCR do we
        # execute the existing Claude + matcher + JEV branch below.
        claude_ocr = auto_mode or claude_test
        gemini_primary_ok = False
        if auto_mode:
            from .auto_v3 import recognize_gemini_primary
            started_gemini = time.perf_counter()
            try:
                classify_result, dzial, result, gemini_timings = recognize_gemini_primary(
                    files, session, document.magazyn,
                    event_callback=save_ai_event, cooldown_store=cooldown_store,
                )
                timings.update(gemini_timings)
                gemini_primary_ok = True
                save_ai_event({
                    "status":"completed", "stage":"auto_gemini_primary",
                    "provider":"Gemini", "model":result.used_provider,
                    "label":"AUTO: główny OCR Gemini",
                    "reason":f"Gemini odczytał {len(result.pozycje)} pozycji ({dzial}). Claude nie został użyty.",
                    "step":None, "total_steps":None,
                    "duration_ms":_elapsed_ms(started_gemini),
                    "attempt":1, "target":None,
                    "created_at":datetime.now(timezone.utc).isoformat(),
                })
            except (
                AllProvidersFailedError, OCRProviderError, OCRUnparsableResponseError,
                RuntimeError, TimeoutError, ValueError,
            ) as gemini_error:
                # Do not silently switch to a paid API, or run Opus on every doc.
                # One Claude Sonnet read is the fallback for unavailable or
                # unusable Gemini OCR. Error content is not logged to users.
                logger.warning("AUTO: Gemini unavailable; selecting Claude fallback: %s",
                               type(gemini_error).__name__)
                save_ai_event({
                    "status":"skipped", "stage":"auto_gemini_primary",
                    "provider":"Gemini", "model":"gemini-3.5-flash-lite",
                    "label":"AUTO: Gemini niedostępny — Claude zapasowy",
                    "reason":"Darmowy Gemini nie oddał użytecznego wyniku. Uruchomiono Claude Sonnet.",
                    "step":None, "total_steps":None,
                    "duration_ms":_elapsed_ms(started_gemini),
                    "attempt":1, "target":None,
                    "created_at":datetime.now(timezone.utc).isoformat(),
                })
        if claude_ocr and not gemini_primary_ok:
            # Claude only reads images. Business logic + all catalog decisions
            # continue through the existing matcher and JEV ACTIVE below.
            from .claude_bridge import missing_header_fields, run_claude_host_bridge
            from app.modules.ocr.pipeline_elektryka import _build_item
            from app.modules.ocr.pipeline_hydraulika import _build_item_hydraulika
            from app.modules.matcher.core_hydraulika import DEFAULT_SPECIAL_RULES_HYDRAULIKA

            dzial = "auto" if auto_mode else document.source_type.removeprefix("claude_jev_test_")
            # Claude Sonnet is now a true fallback: do not call Gemini again,
            # and do not start any independent model audit in parallel.
            raw_rows, ocr_seconds, header = run_claude_host_bridge(
                document_id, files, dzial, include_header=True,
            )
            if auto_mode:
                save_ai_event({
                    "status":"completed", "stage":"auto_claude_fallback",
                    "provider":"Claude", "model":"sonnet",
                    "label":"AUTO: zapasowy OCR Claude",
                    "reason":f"Claude przejął OCR po niedostępnym Gemini: {len(raw_rows)} pozycji.",
                    "step":None, "total_steps":None,
                    "duration_ms":int(ocr_seconds*1000),
                    "attempt":1, "target":None,
                    "created_at":datetime.now(timezone.utc).isoformat(),
                })
            if auto_mode:
                from .auto_v3 import classify_auto_dzial
                dzial, confidence, classification_method = classify_auto_dzial(raw_rows)
                classify_result = SimpleNamespace(confidence=confidence)
                save_ai_event({
                    "status": "completed", "stage": "auto_classification",
                    "provider": "AUTO", "model": "header-and-materials",
                    "label": "AUTO: rozpoznanie działu",
                    "reason": f"{dzial}: {classification_method} ({confidence:.0f}%).",
                    "step": None, "total_steps": None, "duration_ms": 0,
                    "attempt": 1, "target": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            catalog = Catalog.from_db(session, dzial=dzial)
            if dzial == "hydraulika":
                positions = [_build_item_hydraulika(row, catalog, document.magazyn)
                             for row in raw_rows]
            else:
                special_rules = rules_from_db(session)
                positions = [_build_item(row, catalog, special_rules, document.magazyn)
                             for row in raw_rows]

            # Fallback is one Claude Sonnet OCR only. Flag uncertain rows
            # for human review; automatic Opus would defeat fast failover.
            for row, position in zip(raw_rows, positions):
                if (row.get("_uncertain") or
                    (position.ilosc_wydana is None and position.ilosc_zuzyta is None)
                    or position.match.quality == "bad"):
                    position.needs_review = True
                    position.form_note = (position.form_note or "") + (
                        " AUTO: niepewny odczyt Claude — sprawdź skan."
                    )
            result = SimpleNamespace(
                numer_projektu=header["numer_projektu"],
                pracownik=header["pracownik"],
                numer_plomby=None if dzial == "hydraulika" else header["numer_plomby"],
                used_provider="Multiplekser AUTO (Gemini niedostępny → Claude Sonnet + JEV)" if auto_mode else "Claude Sonnet + JEV (test)",
                rejected_count=0, pozycje=positions,
            )
            absent=missing_header_fields(dzial,header)
            save_ai_event({
                "status": "rejected" if absent else "completed",
                "stage": "header_ocr", "provider": "Claude", "model": "sonnet",
                "label": "Nagłówek wydawki",
                "reason": ("Nieodczytane pola: "+", ".join(absent)+". Sprawdź skan i uzupełnij ręcznie.")
                          if absent else (
                              "Numer projektu i pracownik odczytane."
                              if dzial == "hydraulika" else
                              "Numer projektu, pracownik i numer plomby odczytane."
                          ),
                "step": None, "total_steps": None,
                "duration_ms": 0, "attempt": 1, "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            if not auto_mode:
                classify_result = SimpleNamespace(confidence=1.0)
            timings["timing_claude_ocr"] = int(ocr_seconds * 1000)
            save_ai_event({
                "status": "completed", "stage": "auto_ocr" if auto_mode else "claude_test_ocr",
                "provider": "Claude", "model": "sonnet",
                "label": "Multiplekser AUTO" if auto_mode else "Claude + JEV (test)",
                "reason": f"Odczytano {len(positions)} pozycji na {len(files)} stronach.",
                "step": None, "total_steps": None, "duration_ms": int(ocr_seconds * 1000),
                "attempt": 1, "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
        elif not claude_ocr:
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
        if not claude_ocr:
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
        qty_before_jev = [(item.get("ilosc_wydana"), item.get("ilosc_zuzyta"))
                          for item in items] if claude_ocr else []
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


        if claude_ocr:
            # Never advertise OCR->JEV as fully confirmed if TypeSafe did not
            # answer for some rows. Preserve original OCR quantities without
            # making up a match/code when an external service is unavailable.
            answered = {r.get("sequence") for r in active_jev_rows}
            missing = 0
            for i, item in enumerate(items):
                before = qty_before_jev[i]
                if (item.get("ilosc_wydana"), item.get("ilosc_zuzyta")) != before:
                    item["ilosc_wydana"], item["ilosc_zuzyta"] = before
                    item["needs_review"] = True
                    item["form_note"] = (item.get("form_note") or "") + " JEV: ilość przywrócona do odczytu Claude."
                if i not in answered:
                    missing += 1
                    item["needs_review"] = True
                    item["form_note"] = (item.get("form_note") or "") + " JEV: brak potwierdzenia kodu, sprawdź ręcznie."
            confirmed = sum(
                bool(item.get("match_kod")) and item.get("match_quality") == "ok"
                for item in items
            )
            needs_check = len(items) - confirmed
            save_ai_event({
                "status": "completed" if not missing and needs_check == 0 else "rejected",
                "stage": "jev_active", "provider": "TypeSafe", "model": None,
                "label": "JEV — decyzje o kodach",
                "reason": f"JEV odpowiedział na {len(answered)}/{len(items)} pozycji; "
                          f"kody OK: {confirmed}/{len(items)}; "
                          f"do sprawdzenia/brak kodu: {needs_check}. "
                          + (f"{missing} bez odpowiedzi JEV." if missing else ""),
                "step": None, "total_steps": None,
                "duration_ms": timings["timing_jev_active"],
                "attempt": 1, "target": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

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
        if not claude_ocr:
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
            if not claude_ocr:
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
                and completed.source_type != "auto_v3"
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


def dispatch_claude_ocr_task(document_id: str) -> None:
    """Claude Pro has its own serial queue so quota waits cannot block Gemini OCR."""
    process_ocr_document.apply_async(args=(document_id,), queue="claude")


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
