"""
Etap 2: FastAPI wystawiajacy modul Matcher jako endpoint.
Katalog wczytywany z PostgreSQL (Catalog.from_db) i trzymany w pamieci procesu -
odswiezany dopiero po restarcie (importu dokonuje osobny skrypt scripts/import_catalog.py).
"""
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.db import SessionLocal
from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog

app = FastAPI(title="Multiplekser Elektryka API", version="0.2.0-etap2")

_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        session = SessionLocal()
        try:
            _catalog = Catalog.from_db(session)
        finally:
            session.close()
    return _catalog


class MatchRequest(BaseModel):
    query: str
    dominant_country: str | None = None


class MatchResponse(BaseModel):
    kod: str | None
    nazwa: str | None
    quality: str
    ratio: float
    jm: str | None


@app.get("/health")
def health():
    return {"status": "ok", "stage": 2}


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest):
    catalog = get_catalog()
    result = match_against_catalog(req.query, catalog, dominant_country=req.dominant_country)
    return MatchResponse(
        kod=result.kod, nazwa=result.nazwa, quality=result.quality,
        ratio=result.ratio, jm=result.jm_override,
    )
