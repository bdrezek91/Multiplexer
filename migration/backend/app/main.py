"""
Etap 4: FastAPI z pelnym CRUD produktow (app/modules/products/router.py) i /match jako
pelnoprawny serwis - katalog i reguly specjalne czytane z sesji DB PER REQUEST (Depends(get_db)),
bez globalnego cache w pamieci procesu (byl w Etapach 2-3) - zeby CRUD od razu widzial swiezy stan.
"""
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.matcher import match_against_catalog, rules_from_db
from app.modules.products import Catalog
from app.modules.products.router import router as products_router

app = FastAPI(title="Multiplekser Elektryka API", version="0.4.0-etap4")
app.include_router(products_router)


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
    return {"status": "ok", "stage": 4}


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest, session: Session = Depends(get_db)):
    catalog = Catalog.from_db(session)
    special_rules = rules_from_db(session)
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
