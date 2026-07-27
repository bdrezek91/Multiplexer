"""Endpointy auth (Etap 5): logowanie, odswiezanie tokenu, dane biezacego uzytkownika."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db import get_db

from . import repository
from .deps import get_current_user
from .models import UserModel
from .schemas import AccessToken, RefreshRequest, Token, UserOut
from .security import InvalidTokenError, create_access_token, create_refresh_token, decode_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_db)):
    user = repository.get_user_by_email(session, form_data.username)
    if user is None or not user.active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidlowy email lub haslo")
    uid = str(user.id)
    return Token(access_token=create_access_token(uid), refresh_token=create_refresh_token(uid))


@router.post("/refresh", response_model=AccessToken)
def refresh(data: RefreshRequest, session: Session = Depends(get_db)):
    try:
        user_id = decode_token(data.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidlowy lub wygasly refresh token")
    user = repository.get_user_by_id(session, user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Uzytkownik nie istnieje lub jest nieaktywny")
    return AccessToken(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: UserModel = Depends(get_current_user)):
    return UserOut(
        id=str(user.id), email=user.email, rola=user.rola,
        magazyny_dostepne=user.magazyny_dostepne or [], active=user.active,
    )
