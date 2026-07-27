"""
Etap 5: JWT + RBAC. /match wymaga zalogowanego uzytkownika; parametr `magazyn` ograniczony do
`magazyny_dostepne` przypisanych uzytkownikowi (admin bez ograniczen - ma dostep do wszystkich
magazynow). CRUD /products chroniony w app/modules/products/router.py (odczyt kazdy zalogowany,
zapis tylko admin).
"""
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.matcher import magazyn_key, match_against_catalog, rules_from_db
from app.modules.products import Catalog
from app.modules.products.router import router as products_router
from app.modules.users import get_current_user
from app.modules.users.models import UserModel
from app.modules.users.router import router as auth_router

app = FastAPI(title="Multiplekser Elektryka API", version="0.5.0-etap5")
app.include_router(auth_router)
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
    return {"status": "ok", "stage": 5}


def _check_magazyn_access(user: UserModel, magazyn: str | None) -> None:
    if not magazyn or user.rola == "admin":
        return
    allowed = {magazyn_key(m) for m in (user.magazyny_dostepne or [])}
    if magazyn_key(magazyn) not in allowed:
        raise HTTPException(status_code=403, detail=f"Brak dostepu do magazynu {magazyn!r}")


@app.post("/match", response_model=MatchResponse)
def match(req: MatchRequest, session: Session = Depends(get_db), user: UserModel = Depends(get_current_user)):
    _check_magazyn_access(user, req.magazyn)

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
