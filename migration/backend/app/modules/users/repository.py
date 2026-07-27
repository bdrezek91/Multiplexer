"""Repozytorium uzytkownikow (Etap 5)."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from .models import UserModel
from .security import hash_password


class DuplicateEmailError(Exception):
    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Uzytkownik o adresie {email!r} juz istnieje")


def get_user_by_email(session: Session, email: str) -> UserModel | None:
    return session.query(UserModel).filter(UserModel.email == email).first()


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
