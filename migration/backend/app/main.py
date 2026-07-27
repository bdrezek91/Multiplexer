"""
Etap 3: FastAPI wystawiajacy modul Matcher jako endpoint.
Katalog i reguly specjalne wczytywane z PostgreSQL i trzymane w pamieci procesu - odswiezane
dopiero po restarcie (importu dokonuja osobne skrypty scripts/import_catalog.py i
scripts/import_special_rules.py).
"""
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.db import SessionLocal
from app.modules.matcher import SpecialRule, match_against_catalog, rules_from_db
from app.modules.products import Catalog

app = FastAPI(title="Multiplekser Elektryka API", version="0.3.0-etap3")

_catalog: Catalog | None = None
_special_rules: list[SpecialRule] | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        session = SessionLocal()
        try:
            _catalog = Catalog.from_db(session)
        finally:
            session.close()
    return _catalog


def get_special_rules() -> list[SpecialRule]:
    global _special_rules
    if _special_rules is None:
        session = SessionLocal()
        try:
            _special_rules = rules_from_db(session)
        finally:
            session.close()
    return _special_rules


class MatchRequest(BaseModel):
    query: str
    dominant_country: str | None = None
    magazyn: str | None = None


class MatchResponse(BaseModel):
    kod: str | None
    nazwa: str | None
    quality: str
    ratio: float
    jm: str | None


@app.get("/health")
def health():
    return {"status": "ok", "stage": 3}


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest):
    catalog = get_catalog()
    special_rules = get_special_rules()
    result = match_against_catalog(
        req.query, catalog,
        dominant_country=req.dominant_country,
        magazyn=req.magazyn,
        special_rules=special_rules,
    )
    return MatchResponse(
        kod=result.kod, nazwa=result.nazwa, quality=result.quality,
        ratio=result.ratio, jm=result.jm_override,
    )
