"""Repozytorium uzytkownikow (Etap 5; CRUD + reset hasla od Etapu 11)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import UserModel
from .security import hash_password

ROLES = ("admin", "elektryk")


class DuplicateEmailError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Użytkownik o adresie {email!r} już istnieje")


class UserNotFoundError(Exception):
    def __init__(self, user_id):
        self.user_id = user_id
        super().__init__(f"Użytkownik {user_id!r} nie istnieje")


def get_user_by_email(session: Session, email: str) -> UserModel | None:
    return session.query(UserModel).filter(UserModel.email == email).first()


def list_users(session: Session) -> list[UserModel]:
    return session.query(UserModel).order_by(UserModel.email).all()


def get_user_by_id(session: Session, user_id: str) -> UserModel | None:
    try:
        uid = uuid.UUID(str(user_id))
    except (ValueError, TypeError, AttributeError):
        return None
    return session.query(UserModel).filter(UserModel.id == uid).first()


def create_user(
    session: Session,
    email: str,
    password: str,
    rola: str = "elektryk",
    magazyny_dostepne: list[str] | None = None,
) -> UserModel:
    if get_user_by_email(session, email) is not None:
        raise DuplicateEmailError(email)

    user = UserModel(
        email=email,
        hashed_password=hash_password(password),
        rola=rola,
        magazyny_dostepne=magazyny_dostepne or [],
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user(
    session: Session,
    user_id: str,
    *,
    email: str,
    rola: str,
    magazyny_dostepne: list[str],
    active: bool,
) -> UserModel:
    """Pelna zamiana pol edytowalnych (jak PUT /products/{kod}) - HASLO NIE jest tu zmieniane,
    patrz set_password() (osobny endpoint - zmiana hasla to inna operacja niz edycja profilu,
    ktora nie powinna wymagac podawania nowego hasla przy kazdej edycji)."""
    user = get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    existing = get_user_by_email(session, email)
    if existing is not None and existing.id != user.id:
        raise DuplicateEmailError(email)

    user.email = email
    user.rola = rola
    user.magazyny_dostepne = magazyny_dostepne
    user.active = active
    session.commit()
    session.refresh(user)
    return user


def set_password(session: Session, user_id: str, new_password: str) -> UserModel:
    user = get_user_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    user.hashed_password = hash_password(new_password)
    session.commit()
    session.refresh(user)
    return user
