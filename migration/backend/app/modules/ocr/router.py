"""Endpoint OCR (Etap 6) - SYNCHRONICZNY (bez Celery/MinIO - odlozone do kolejnego etapu, patrz
docs/RAPORT_ETAP_6.md). Zadanie moze trwac do `ocr_timeout_seconds` (domyslnie 90s na krok
lancucha) - akceptowalne dla malej skali, do zamiany na async przy realnym ruchu."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.matcher import rules_from_db
from app.modules.products import Catalog
from app.modules.users import get_current_user
from app.modules.users.deps import check_magazyn_access
from app.modules.users.models import UserModel

from . import image as ocr_image
from .chain import AllProvidersFailedError
from .pipeline import OCRUnparsableResponseError, recognize_document
from .providers import OCRProviderError
from .schemas import OCRItemOut, OCRMatchOut, OCRResultOut

router = APIRouter(prefix="/ocr", tags=["ocr"])

_PDF_MIME = "application/pdf"


@router.post("/recognize", response_model=OCRResultOut)
async def recognize(
    plik: UploadFile = File(...),
    magazyn: str | None = Form(default=None),
    session: Session = Depends(get_db),
    user: UserModel = Depends(get_current_user),
):
    check_magazyn_access(user, magazyn)

    raw = await plik.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Pusty plik")

    is_pdf = plik.content_type == _PDF_MIME or (plik.filename or "").lower().endswith(".pdf")
    if is_pdf:
        file_bytes, mime = raw, _PDF_MIME
    else:
        # Skalowanie w dol przed wyslaniem do AI (port downscaleImage() - mniejszy upload =
        # szybsza odpowiedz). PDF wysylany natywnie do Gemini, bez renderowania na obrazy
        # (potrzebne dopiero dla dostawcow bez natywnej obslugi PDF - nieprzeniesieni w tym etapie).
        file_bytes, mime = ocr_image.downscale_image(raw), "image/jpeg"

    catalog = Catalog.from_db(session)
    special_rules = rules_from_db(session)

    try:
        result = await recognize_document(file_bytes, mime, catalog, special_rules, magazyn=magazyn)
    except OCRUnparsableResponseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AllProvidersFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OCRProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return OCRResultOut(
        numer_projektu=result.numer_projektu,
        used_provider=result.used_provider,
        rejected_count=result.rejected_count,
        pozycje=[
            OCRItemOut(
                rozpoznana_nazwa=it.rozpoznana_nazwa,
                ilosc_wydana=it.ilosc_wydana,
                ilosc_zuzyta=it.ilosc_zuzyta,
                uwagi=it.uwagi,
                confidence=it.confidence,
                needs_review=it.needs_review,
                off_form=it.off_form,
                form_note=it.form_note,
                match=OCRMatchOut(
                    kod=it.match.kod, nazwa=it.match.nazwa, quality=it.match.quality,
                    ratio=it.match.ratio, jm=it.match.jm_override,
                ),
            )
            for it in result.pozycje
        ],
    )
