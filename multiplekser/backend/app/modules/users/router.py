"""Endpointy auth (Etap 5): logowanie, odswiezanie tokenu, dane biezacego uzytkownika.
Endpointy zarzadzania uzytkownikami (Etap 11, admin-only) - patrz osobny `users_router` nizej.

UWAGA: bez `from __future__ import annotations` (usuniete 2026-07-30, wczesniej tu bylo) -
swiadomie. @limiter.limit() (slowapi) opakowuje login() swoim wrapperem przez functools.wraps,
ktory NIE dziedziczy __globals__ oryginalnej funkcji (to niemozliwe do przekazania w Pythonie).
Z postponed evaluation adnotacje typow sa stringami w momencie definicji, a FastAPI rozwiazuje
je pozniej przez __globals__ funkcji, ktore dla wrappera slowapi wskazuja na modul slowapi, nie
na ten plik - OAuth2PasswordRequestForm nie jest tam widoczny, wiec FastAPI dostaje
nierozwiazany ForwardRef zamiast klasy i wywala sie przy starcie. Bez postponed evaluation
adnotacje sa prawdziwymi obiektami klas juz w momencie definicji funkcji, wiec ten problem
w ogole nie wystepuje. Python 3.11 i tak nie wymaga tego importu (natywne `X | Y`/`list[X]`)."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.rate_limit import limiter

from . import repository
from .deps import get_current_user, require_admin
from .lockout import get_login_lockout_store
from .models import UserModel
from .schemas import (
    AccessToken, PasswordResetRequest, RefreshRequest, Token, UserCreate, UserOut, UserUpdate,
)
from .security import (
    InvalidTokenError, create_access_token, create_refresh_token, decode_refresh_token,
    verify_password,
)
from .token_blacklist import get_token_blacklist_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


@router.post("/token", response_model=Token)
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_db),
):
    # Blokada per-konto (Redis, patrz lockout.py) - uzupelnia rate limiting per-IP powyzej
    # (@limiter.limit), ktory nie chroni przed rozproszonym atakiem na to samo konto z wielu
    # adresow IP. Sprawdzana PRZED odczytem uzytkownika/haslem - zablokowane konto nie
    # ujawnia nawet czy haslo bylo poprawne.
    lockout_store = get_login_lockout_store()
    locked_seconds = lockout_store.remaining_seconds(form_data.username)
    if locked_seconds > 0:
        logger.warning("Logowanie zablokowane (zbyt wiele nieudanych prob)", extra={"email": form_data.username})
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Konto tymczasowo zablokowane po zbyt wielu nieudanych próbach logowania - "
                f"spróbuj ponownie za {locked_seconds // 60 + 1} min."
            ),
        )
    user = repository.get_user_by_email(session, form_data.username)
    if user is None or not user.active or not verify_password(form_data.password, user.hashed_password):
        lockout_store.record_failure(form_data.username)
        logger.warning("Nieudane logowanie", extra={"email": form_data.username})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy email lub hasło")
    lockout_store.reset(form_data.username)
    uid = str(user.id)
    logger.info("Logowanie", extra={"user_id": uid, "email": user.email})
    return Token(access_token=create_access_token(uid), refresh_token=create_refresh_token(uid))


@router.post("/refresh", response_model=AccessToken)
def refresh(data: RefreshRequest, session: Session = Depends(get_db)):
    try:
        refresh_data = decode_refresh_token(data.refresh_token)
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy lub wygasły refresh token")
    if get_token_blacklist_store().is_revoked(refresh_data.jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token został unieważniony (wylogowano)")
    user = repository.get_user_by_id(session, refresh_data.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Użytkownik nie istnieje lub jest nieaktywny")
    return AccessToken(access_token=create_access_token(str(user.id)))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshRequest) -> None:
    """Uniewaznia refresh token (wpisuje jego 'jti' na blackliste w Redis do naturalnego
    wygasniecia - patrz token_blacklist.py). Celowo NIE zwraca 401 na niepoprawnym/juz
    wygaslym/juz uniewaznionym tokenie - wylogowanie ma byc idempotentne z punktu widzenia
    klienta (frontend i tak kasuje lokalnie zapisane tokeny niezaleznie od wyniku tego
    zadania, patrz frontend/src/api/auth.ts)."""
    try:
        refresh_data = decode_refresh_token(data.refresh_token)
    except InvalidTokenError:
        return
    get_token_blacklist_store().revoke(refresh_data.jti, refresh_data.expires_in_seconds)


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
