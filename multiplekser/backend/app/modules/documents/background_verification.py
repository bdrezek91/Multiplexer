"""Drugi, niezalezny odczyt dokumentu wykonywany po status=done."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Mapping, Optional

from sqlalchemy.orm import Session

from app.modules.matcher import rules_from_db
from app.modules.matcher.special_rules import GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY
from app.modules.ocr.chain import OCRChainEventCallback, quantity_verification_chain
from app.modules.ocr.cooldown import OCRCooldownStore, get_ocr_cooldown_store
from app.modules.ocr.parsing import parse_float_loose
from app.modules.ocr.pipeline_elektryka import recognize_document
from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
from app.modules.products import Catalog

from . import repository
from .ocr_processing import _download_and_prepare
from .task_telemetry import _background_queue_wait_ms, _elapsed_ms, _timing_event

logger = logging.getLogger(__name__)


_FULL_REREAD_MISMATCH_NOTE = (
    "Druga, pełna kontrola AI całego dokumentu wskazuje inną ilość dla tego wiersza - "
    "zweryfikuj ręcznie na oryginale."
)


async def _check_full_document_consistency(
    files: list[tuple[bytes, str]],
    items: list[dict],
    dzial: str,
    catalog: Catalog,
    special_rules,
    magazyn: Optional[str],
    session: Session,
    document_id,
    event_callback: OCRChainEventCallback,
    cooldown_store: OCRCooldownStore,
    log_context: Mapping[str, object],
) -> bool:
    """Druga, PELNA, niezalezna kontrola calego dokumentu (2026-09-18) - porownuje KAZDA pozycje
    z drugim, niezaleznym pelnym odczytem calego dokumentu (nie tylko wybrane grupy podobnych
    etykiet - wczesniejsza, waskaza wersja tego mechanizmu, _check_row_group_alignment,
    ograniczona do grup wykrytych przez row_groups.py, zostala usunieta 2026-09-18: prawdziwa
    przyczyna powtarzajacego sie bledu "zla ilosc w sasiednim wierszu" okazala sie byc falszywe
    wykrywanie skosu skanu - patrz ocr/image.py, _detect_skew_angle_deg - a nie niedoskonalosc
    modelu AI, wiec waska kontrola grup przestala byc warta swojego kosztu/czasu; ta funkcja
    zostaje jako ogolny, tanszy w czasie safety-net na przyszlosc).

    Uzywa WYLACZNIE darmowego lancucha Gemini (quantity_verification_chain) - NIE innego
    dostawcy (podobny, pelny cross-check z OpenAI byl juz probowany i porzucony z powodu duzego
    szumu, git historia ocr/crosscheck.py). Best-effort - blad/niedostepnosc modelu NIGDY nie
    blokuje calego dokumentu. NIGDY nie nadpisuje ani nie dodaje zgadywanych pozycji - tylko
    oznacza rozbieznosci do recznej weryfikacji, zostawiajac decyzje co bylo faktycznie na
    kartce czlowiekowi."""
    try:
        if dzial == "hydraulika":
            confirm = await recognize_document_hydraulika(
                files, catalog, magazyn=magazyn, chain=quantity_verification_chain(),
                log_context={**dict(log_context), "ai_stage_override": "full_document_verification"},
                event_callback=event_callback, cooldown_store=cooldown_store,
            )
        else:
            confirm = await recognize_document(
                files, catalog, special_rules or [], magazyn=magazyn, chain=quantity_verification_chain(),
                log_context={**dict(log_context), "ai_stage_override": "full_document_verification"},
                event_callback=event_callback, cooldown_store=cooldown_store,
            )
    except Exception:
        logger.warning("Pelna kontrola spojnosci dokumentu nieudana - pomijam", exc_info=True)
        return False

    confirm_by_label: dict[str, tuple[Optional[float], Optional[float]]] = {}
    for it in confirm.pozycje:
        wydana = parse_float_loose(it.ilosc_wydana) if it.ilosc_wydana is not None else None
        zuzyta = parse_float_loose(it.ilosc_zuzyta) if it.ilosc_zuzyta is not None else None
        confirm_by_label[it.rozpoznana_nazwa] = (wydana, zuzyta)

    main_labels = {item["rozpoznana_nazwa"] for item in items}

    for item in items:
        label = item["rozpoznana_nazwa"]
        confirm_qty = confirm_by_label.get(label)
        main_qty = (item["ilosc_wydana"], item["ilosc_zuzyta"])
        if confirm_qty == main_qty:
            continue  # zgodnosc obu niezaleznych, pelnych odczytow - bez zmian

        item["needs_review"] = True
        item["ilosc_z_dodatkowej_kontroli"] = True
        existing_note = item.get("form_note") or ""
        item["form_note"] = (
            f"{existing_note} | {_FULL_REREAD_MISMATCH_NOTE}" if existing_note else _FULL_REREAD_MISMATCH_NOTE
        )
        try:
            repository.log_row_group_flag(
                session, document_id=document_id, dzial=dzial, rozpoznana_nazwa=label,
                kind="full_reread_mismatch",
                main_ilosc_wydana=main_qty[0], main_ilosc_zuzyta=main_qty[1],
                second_ilosc_wydana=confirm_qty[0] if confirm_qty else None,
                second_ilosc_zuzyta=confirm_qty[1] if confirm_qty else None,
            )
        except Exception:
            logger.warning("Nie udalo sie zapisac logu full-reread-mismatch", exc_info=True)

    # Etykiety znalezione TYLKO w drugim, kontrolnym odczycie (mozliwe "ofiary" przesuniecia) -
    # NIE dodajemy ich automatycznie (druga kontrola sama bywa niepewna), tylko widoczny trop
    # w "Przebiegu AI".
    for label, (wydana, zuzyta) in confirm_by_label.items():
        if label in main_labels or (wydana is None and zuzyta is None):
            continue
        if event_callback is not None:
            try:
                event_callback({
                    "status": "no_result", "stage": "full_document_verification",
                    "provider": None, "model": None, "label": None,
                    "reason": (
                        f'Druga, pełna kontrola AI sugeruje pozycję "{label}" (ilość wydana: '
                        f'{wydana}, zużyta: {zuzyta}), której NIE ma w głównym odczycie - NIE '
                        f'dodano automatycznie, zweryfikuj ręcznie na oryginale.'
                    ),
                    "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
                    "target": label, "created_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                logger.warning("Nie udalo sie zapisac zdarzenia AI dla full-reread", exc_info=True)
        try:
            repository.log_row_group_flag(
                session, document_id=document_id, dzial=dzial, rozpoznana_nazwa=label,
                kind="full_reread_missing", main_ilosc_wydana=None, main_ilosc_zuzyta=None,
                second_ilosc_wydana=wydana, second_ilosc_zuzyta=zuzyta,
            )
        except Exception:
            logger.warning("Nie udalo sie zapisac logu full-reread-missing", exc_info=True)

    return True




def _background_review_item(row) -> Optional[dict]:
    """Buduje stan do drugiego OCR tak, jak wygladal PRZED automatycznymi regulami biznesowymi.

    Automatycznie dopisanych pozycji (np. zasilacz LED) nie ma na papierze, wiec nie wolno ich
    porownywac z drugim odczytem. Gniazdo podwojne jest w systemie mnozone x2 dopiero po OCR;
    kontrola obrazu musi porownac sie z surowa iloscia z kartki, czyli przed mnoznikiem.
    """
    form_note = str(getattr(row, "form_note", "") or "")
    if form_note.startswith("Dodano automatycznie"):
        return None

    wydana = getattr(row, "ilosc_wydana", None)
    zuzyta = getattr(row, "ilosc_zuzyta", None)
    kod = str(getattr(row, "match_kod", "") or "").strip()
    uwagi = str(getattr(row, "uwagi", "") or "").lower()
    if kod in GNIAZDO_PODTYNKOWE_Z_KLAPKA_KODY and "podwojona automatycznie" in uwagi:
        wydana = wydana / 2 if wydana is not None else None
        zuzyta = zuzyta / 2 if zuzyta is not None else None

    return {
        "rozpoznana_nazwa": row.rozpoznana_nazwa,
        "ilosc_wydana": wydana,
        "ilosc_zuzyta": zuzyta,
        "needs_review": row.needs_review,
        "ilosc_z_dodatkowej_kontroli": row.ilosc_z_dodatkowej_kontroli,
        "form_note": form_note,
    }


def run_full_document_verification_task(document_id: str, session: Session) -> None:
    """Drugi pelny odczyt Gemini uruchamiany PO zapisaniu glownego wyniku.

    Nie zmienia dopasowan ani ilosci. Moze tylko ustawic needs_review,
    ilosc_z_dodatkowej_kontroli i dopisac ostrzezenie do form_note / ai_trace.
    """
    from .storage import get_storage

    document = repository.get_document(session, document_id)
    if document is None or document.status != "done" or document.dzial not in {"elektryka", "hydraulika"}:
        return

    background_started = time.perf_counter()
    background_timings: dict[str, int] = {}
    queue_wait = _background_queue_wait_ms(document)
    if queue_wait is not None:
        background_timings["timing_background_queue_wait"] = queue_wait

    try:
        stage_started = time.perf_counter()
        files = list(_download_and_prepare(get_storage, document.file_key, document.mime))
        for extra in document.extra_files:
            files += _download_and_prepare(get_storage, extra.file_key, extra.mime)
        background_timings["timing_background_prepare"] = _elapsed_ms(stage_started)

        review_rows = []
        review_items = []
        for row in document.items:
            review = _background_review_item(row)
            if review is None:
                continue
            review_rows.append(row)
            review_items.append(review)

        def save_ai_event(event: dict[str, object]) -> None:
            repository.append_ai_trace_event(session, document, event)

        catalog = Catalog.from_db(session, dzial=document.dzial)
        special_rules = None if document.dzial == "hydraulika" else rules_from_db(session)
        stage_started = time.perf_counter()
        verification_ok = asyncio.run(_check_full_document_consistency(
            files,
            review_items,
            document.dzial,
            catalog,
            special_rules,
            document.magazyn,
            session,
            document.id,
            save_ai_event,
            get_ocr_cooldown_store(),
            {"document_id": document_id, "background_check": True},
        ))
        background_timings["timing_background_verification"] = _elapsed_ms(stage_started)
        if not verification_ok:
            background_timings["timing_background_total"] = _elapsed_ms(background_started)
            events = [_timing_event(stage, duration) for stage, duration in background_timings.items()]
            events.append({
                "status": "failed", "stage": "full_document_verification",
                "provider": None, "model": None, "label": None,
                "reason": "Pełna kontrola dokumentu w tle nie zakończyła się poprawnym odczytem.",
                "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
                "target": None, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            repository.append_ai_trace_events(session, document, events)
            return

        # Kolejnosc review_items odpowiada DocumentItem.sequence (relationship ma order_by).
        # Druga kontrola nie dotyka ilosci ani kodow - tylko flagi/komunikat dla operatora.
        for row, review in zip(review_rows, review_items):
            row.needs_review = bool(review["needs_review"])
            row.ilosc_z_dodatkowej_kontroli = bool(review["ilosc_z_dodatkowej_kontroli"])
            row.form_note = str(review["form_note"] or "")
        session.commit()
        background_timings["timing_background_total"] = _elapsed_ms(background_started)
        events = [_timing_event(stage, duration) for stage, duration in background_timings.items()]
        events.append({
            "status": "completed", "stage": "full_document_verification",
            "provider": None, "model": None, "label": None,
            "reason": "Pełna kontrola dokumentu w tle zakończona.",
            "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
            "target": None, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        repository.append_ai_trace_events(session, document, events)
        logger.info(
            "Pelna kontrola dokumentu w tle - zakonczona",
            extra={"document_id": document_id, "dzial": document.dzial},
        )
    except Exception:
        session.rollback()
        logger.warning(
            "Pelna kontrola dokumentu w tle nieudana - wynik glowny pozostaje bez zmian",
            exc_info=True,
            extra={"document_id": document_id},
        )
        try:
            background_timings["timing_background_total"] = _elapsed_ms(background_started)
            events = [_timing_event(stage, duration) for stage, duration in background_timings.items()]
            events.append({
                "status": "failed", "stage": "full_document_verification",
                "provider": None, "model": None, "label": None,
                "reason": "Pełna kontrola dokumentu w tle zakończyła się błędem.",
                "step": None, "total_steps": None, "duration_ms": None, "attempt": None,
                "target": None, "created_at": datetime.now(timezone.utc).isoformat(),
            })
            repository.append_ai_trace_events(session, document, events)
        except Exception:
            session.rollback()
