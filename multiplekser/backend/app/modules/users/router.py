"""Endpointy auth (Etap 5): logowanie, odswiezanie tokenu, dane biezacego uzytkownika.
Endpointy zarzadzania uzytkownikami (Etap 11, admin-only) - patrz osobny `users_router` nizej."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db import get_db

from . import repository
from .deps import get_current_user, require_admin
from .models import UserModel
from .schemas import (
    AccessToken, PasswordResetRequest, RefreshRequest, Token, UserCreate, UserOut, UserUpdate,
)
from .security import InvalidTokenError, create_access_token, create_refresh_token, decode_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_db)):
    user = repository.get_user_by_email(session, form_data.username)
    if user is None or not user.active or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy email lub hasło")
    uid = str(user.id)
    return Token(access_token=create_access_token(uid), refresh_token=create_refresh_token(uid))


@router.post("/refresh", response_model=AccessToken)
def refresh(data: RefreshRequest, session: Session = Depends(get_db)):
    try:
        user_id = decode_token(data.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy lub wygasły refresh token")
    user = repository.get_user_by_id(session, user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Użytkownik nie istnieje lub jest nieaktywny")
    return AccessToken(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(user: UserModel = Depends(get_current_user)):
    return _to_user_out(user)


def _to_user_out(user: UserModel) -> UserOut:
    return UserOut(
        id=str(user.id), email=user.email, rola=user.rola,
        magazyny_dostepne=user.magazyny_dostepne or [], active=user.active,
    )


def _validate_rola(rola: str) -> None:
    if rola not in repository.ROLES:
        raise HTTPException(status_code=400, detail=f"Nieprawidłowa rola: {rola!r} (dozwolone: {repository.ROLES})")


@users_router.get("", response_model=list[UserOut], dependencies=[Depends(require_admin)])
def list_users(session: Session = Depends(get_db)):
    return [_to_user_out(u) for u in repository.list_users(session)]


@users_router.post("", response_model=UserOut, status_code=201, dependencies=[Depends(require_admin)])
def create_user(data: UserCreate, session: Session = Depends(get_db)):
    _validate_rola(data.rola)
    try:
        user = repository.create_user(
            session, email=data.email, password=data.password,
            rola=data.rola, magazyny_dostepne=data.magazyny_dostepne,
        )
    except repository.DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_user_out(user)


@users_router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    data: UserUpdate,
    session: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin),
):
    _validate_rola(data.rola)
    # Ochrona przed samo-zablokowaniem: admin nie moze przez ten endpoint zdezaktywowac
    # wlasnego konta ani zdegradowac sie z roli admin - inaczej ostatni administrator moglby
    # przypadkiem odciac sobie dostep bez mozliwosci cofniecia (brak innej sciezki odzyskania).
    if str(admin.id) == user_id and (not data.active or data.rola != "admin"):
        raise HTTPException(
            status_code=400,
            detail="Nie można zdezaktywować ani zdegradować własnego konta administratora",
        )
    try:
        user = repository.update_user(
            session, user_id, email=data.email, rola=data.rola,
            magazyny_dostepne=data.magazyny_dostepne, active=data.active,
        )
    except repository.UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except repository.DuplicateEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_user_out(user)


@users_router.post("/{user_id}/reset-password", response_model=UserOut, dependencies=[Depends(require_admin)])
def reset_password(user_id: str, data: PasswordResetRequest, session: Session = Depends(get_db)):
    try:
        user = repository.set_password(session, user_id, data.new_password)
    except repository.UserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_user_out(user)
