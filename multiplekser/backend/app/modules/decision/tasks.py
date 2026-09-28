"""Celery task uruchamiajacy Jev Shadow dla calego dokumentu, PO zakonczeniu glownego OCR.

Celowo OSOBNE zadanie Celery (nie czesc run_ocr_task w documents/tasks.py) - zaden timeout
ani blad komunikacji z TypeSafe nie moze opoznic ani zepsuc glownego przetwarzania dokumentu,
ktore widzi uzytkownik (na zyczenie uzytkownika, 2026-09-29: "zeby dzialal razem z Gemini",
ale bez wplywu na wynik - JEV_MODE=shadow). Fail-open per-pozycja jest juz zagwarantowany
przez evaluate_shadow() (jev_shadow.py) - to zadanie tylko je wywoluje dla kazdej pozycji
dokumentu (rownolegle, asyncio.gather) i loguje podsumowanie (structured log) do recznej
analizy zgodnosci matcher-vs-Jev. Nic z tego nie zmienia Document/DocumentItem w bazie."""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.modules.matcher.result import MatchResult
from app.modules.products import Catalog

from ..documents.models import DocumentModel
from .jev_client import jev_enabled
from .jev_shadow import evaluate_shadow
from .models import JevShadowResultModel

logger = logging.getLogger(__name__)


async def _evaluate_all(document: DocumentModel, catalog: Catalog) -> list[dict]:
    coros = []
    rows = []

    for item in document.items:
        nazwa = (item.rozpoznana_nazwa or "").strip()
        if not nazwa:
            continue

        current_match = MatchResult(
            kod=item.match_kod,
            nazwa=item.match_nazwa,
            quality=item.match_quality,
            ratio=item.match_score or 0.0,
            jm_override=item.match_jm,
        )
        rows.append((item, current_match))
        coros.append(evaluate_shadow(
            query_name=nazwa,
            catalog=catalog,
            current_match=current_match,
            dzial=document.dzial or "elektryka",
            magazyn=document.magazyn,
        ))

    if not coros:
        return []

    results = await asyncio.gather(*coros, return_exceptions=True)

    out = []
    for (item, _current_match), result in zip(rows, results):
        if isinstance(result, BaseException):
            logger.warning("Jev shadow - wyjatek dla pozycji, pomijam", exc_info=result)
            continue
        if result is None:
            continue
        out.append({
            "item_id": item.id,
            "rozpoznana_nazwa": item.rozpoznana_nazwa,
            "matcher_kod": result.matcher_kod,
            "jev_kod": result.jev_kod,
            "agrees": result.agrees,
            "matcher_in_shortlist": result.matcher_in_shortlist,
            "confidence": result.confidence,
            "model": result.model,
            "probabilities": result.probabilities,
            "query_features": result.query_features,
            "candidate_codes": [c.kod for c in result.candidates],
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
        })
    return out


def _persist_rows(session: Session, document_id: str, rows: list[dict]) -> None:
    """Upsert wynikow shadow per pozycja. Nie dotyka Document/DocumentItem."""
    for row in rows:
        existing = (
            session.query(JevShadowResultModel)
            .filter(JevShadowResultModel.item_id == row["item_id"])
            .one_or_none()
        )
        values = {
            "document_id": document_id,
            "item_id": row["item_id"],
            "rozpoznana_nazwa": row["rozpoznana_nazwa"],
            "matcher_kod": row["matcher_kod"],
            "jev_kod": row["jev_kod"],
            "agrees": row["agrees"],
            "matcher_in_shortlist": row["matcher_in_shortlist"],
            "confidence": row["confidence"],
            "model": row["model"],
            "probabilities": row["probabilities"],
            "query_features": row["query_features"],
            "candidate_codes": row["candidate_codes"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
        }
        if existing is None:
            session.add(JevShadowResultModel(**values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
    session.commit()


def run_jev_shadow_for_document(document_id: str, session: Session) -> None:
    document = session.get(DocumentModel, document_id)
    if document is None:
        return

    dzial = document.dzial or "elektryka"
    if dzial != "elektryka":
        # Diagnostyka per-atrybut (candidate_diagnostics.py) i query_features sa dzis
        # zaimplementowane tylko dla Elektryki - Hydraulika swiadomie pominieta na tym etapie.
        return

    catalog = Catalog.from_db(session, dzial=dzial)

    try:
        rows = asyncio.run(_evaluate_all(document, catalog))
    except Exception:
        logger.warning(
            "Jev shadow - nieoczekiwany blad dla calego dokumentu, pomijam",
            exc_info=True, extra={"document_id": document_id},
        )
        return

    if not rows:
        return

    try:
        _persist_rows(session, document.id, rows)
    except Exception:
        session.rollback()
        logger.warning(
            "Jev shadow - nie udalo sie zapisac wynikow do bazy",
            exc_info=True,
            extra={"document_id": document_id},
        )

    zgodnosc = sum(1 for r in rows if r["agrees"])
    log_rows = [
        {
            "rozpoznana_nazwa": r["rozpoznana_nazwa"],
            "matcher_kod": r["matcher_kod"],
            "jev_kod": r["jev_kod"],
            "agrees": r["agrees"],
            "confidence": r["confidence"],
            "matcher_in_shortlist": r["matcher_in_shortlist"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
        }
        for r in rows
    ]
    summary = {
        "document_id": document_id,
        "pozycje_ocenione": len(rows),
        "zgodnosc_z_matcherem": zgodnosc,
        "rozbieznosci": len(rows) - zgodnosc,
        "zgodnosc_proc": round(100.0 * zgodnosc / len(rows), 1),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
        "szczegoly": log_rows,
    }
    logger.info(
        "Jev shadow - podsumowanie dokumentu | %s",
        json.dumps(summary, ensure_ascii=False, default=str),
        extra=summary,
    )


@celery_app.task(name="decision.jev_shadow")
def process_jev_shadow(document_id: str) -> None:
    session = SessionLocal()
    try:
        run_jev_shadow_for_document(document_id, session)
    finally:
        session.close()


def dispatch_jev_shadow_task(document_id: str) -> None:
    """Zleca ocene Jev Shadow do Celery - no-op gdy Jev jest wylaczony (JEV_ENABLED=false),
    zeby nie zaśmiecac kolejki zadaniami ktore i tak natychmiast wroca bez wyniku."""
    if not jev_enabled():
        return
    process_jev_shadow.delay(document_id)
