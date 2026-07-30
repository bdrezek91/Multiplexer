"""Silnik SQLAlchemy, sesje i bazowa klasa modeli (Etap 2)."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# SQLite (Multiplekser Portable, patrz docs/RAPORT_PORTABLE_1.md) potrzebuje check_same_thread=
# False - sesje sa otwierane z watku OCR (in-process, nie Celery) i z watku obslugujacego
# zadanie HTTP, nie tylko z tego, ktory utworzyl polaczenie. Bez wplywu na Postgresa (produkcja/
# Docker) - ten connect_arg jest specyficzny dla dialektu sqlite.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
