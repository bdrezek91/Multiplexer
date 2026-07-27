"""
Etap 1: minimalny FastAPI wystawiajacy modul Matcher jako endpoint.
Katalog wczytywany z pliku JSON (tymczasowo) - w Etapie 2 zastapione zapytaniem do PostgreSQL.
"""
import json
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from app.modules.matcher import match_against_catalog
from app.modules.products import Catalog

app = FastAPI(title="Multiplekser Elektryka API", version="0.1.0-etap1")

_CATALOG_PATH = Path(__file__).parent.parent / "tests" / "fixtures" / "baza_elektryka.json"
_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        db = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        _catalog = Catalog.from_json_dict(db)
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
    return {"status": "ok", "stage": 1}


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest):
    catalog = get_catalog()
    result = match_against_catalog(req.query, catalog, dominant_country=req.dominant_country)
    return MatchResponse(
        kod=result.kod, nazwa=result.nazwa, quality=result.quality,
        ratio=result.ratio, jm=result.jm_override,
    )
