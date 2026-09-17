"""Endpoint publiczny dla Comarch ERP Optima (2026-09-17) - CELOWO osobny router, bez prefiksu
/documents i bez zadnej zaleznosci auth: Optima pobiera recepture zwyklym, anonimowym GET (nie
potrafi zalogowac sie ani wyslac Bearer tokena). Bezpieczenstwo opiera sie WYLACZNIE na dlugim,
losowym tokenie w URL (patrz repository.get_document_by_optima_token) - `/documents/{id}` samo
w sobie NIE jest i nie ma stac sie publiczne, ten endpoint nic z niego nie odslania poza tym,
na co token uprawnia (odczyt gotowej receptury TXT).

Read-only z zalozenia: brak jakiegokolwiek POST/PATCH/DELETE tutaj."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.generator import encode_cp1250

from . import repository
from .router import _generate_optima_text

router = APIRouter(prefix="/optima", tags=["optima"])


@router.get("/recipe/{document_id}/{token}.txt")
def get_optima_recipe(document_id: str, token: str, session: Session = Depends(get_db)):
    document = repository.get_document_by_optima_token(session, document_id, token)
    if document is None:
        # Jeden, jednolity 404 dla "zly UUID" / "brak aktywnego linku" / "zly token" - nigdy nie
        # zdradzamy, ktory z tych trzech przypadkow zaszedl (patrz docstring repository.py).
        return PlainTextResponse("Nie znaleziono.", status_code=404)

    if document.status != "done":
        return PlainTextResponse(
            "Dokument nie zostal jeszcze poprawnie przetworzony.", status_code=409,
        )

    text = _generate_optima_text(document, session)
    if not text:
        return PlainTextResponse(
            "Dokument nie ma pozycji z ustawiona iloscia finalna do wygenerowania.",
            status_code=409,
        )

    return Response(
        content=encode_cp1250(text),
        media_type="text/plain; charset=windows-1250",
        headers={
            "Content-Disposition": 'inline; filename="receptura.txt"',
            "Cache-Control": "no-store",
        },
    )
