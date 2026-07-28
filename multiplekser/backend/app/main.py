"""
Etap 7: OCR przeniesiony na potok asynchroniczny (POST /documents + Celery), stary synchroniczny
/ocr/recognize z Etapu 6 usuniety (byl swiadomym, tymczasowym ryzykiem - blokowal request HTTP).
/match wymaga zalogowanego uzytkownika; parametr `magazyn` (tu i w /documents) ograniczony do
`magazyny_dostepne` przypisanych uzytkownikowi (patrz app/modules/users/deps.py:check_magazyn_access
- admin bez ograniczen). CRUD /products chroniony w app/modules/products/router.py (odczyt kazdy
zalogowany, zapis tylko admin).
"""
from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.documents.router import router as documents_router
from app.modules.matcher import match_against_catalog, rules_from_db
from app.modules.products import Catalog
from app.modules.products.router import router as products_router
from app.modules.users import get_current_user
from app.modules.users.deps import check_magazyn_access
from app.modules.users.models import UserModel
from app.modules.users.router import router as auth_router
from app.modules.users.router import users_router

app = FastAPI(title="Multiplekser v1.0.0 API", version="0.7.0-etap7")
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(products_router)
app.include_router(documents_router)


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
    return {"status": "ok", "stage": 7}


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest, session: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    check_magazyn_access(user, req.magazyn)

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
