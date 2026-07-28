"""Zaleznosci FastAPI do autoryzacji (Etap 5) - uzywane przez inne moduly (products, main.py)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.matcher import magazyn_key

from . import repository
from .models import UserModel
from .security import InvalidTokenError, decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Nieprawidłowy lub wygasły token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_db)) -> UserModel:
    try:
        user_id = decode_token(token, expected_type="access")
    except InvalidTokenError:
        raise _UNAUTHORIZED
    user = repository.get_user_by_id(session, user_id)
    if user is None or not user.active:
        raise _UNAUTHORIZED
    return user


def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    if user.rola != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wymagana rola: admin")
    return user


def check_magazyn_access(user: UserModel, magazyn: str | None) -> None:
    """Uzywane wszedzie tam, gdzie endpoint przyjmuje magazyn (np. /match, /ocr/recognize) -
    admin bez ograniczen, inne role tylko w ramach magazyny_dostepne."""
    if not magazyn or user.rola == "admin":
        return
    allowed = {magazyn_key(m) for m in (user.magazyny_dostepne or [])}
    if magazyn_key(magazyn) not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Brak dostępu do magazynu {magazyn!r}")
