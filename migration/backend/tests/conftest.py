import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser_test",
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "baza_elektryka.json"


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Sesja izolowana per-test: rollback po tescie, nawet jesli kod pod testem robi commit()."""
    connection = db_engine.connect()
    trans = connection.begin()
    session_factory = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = session_factory()
    yield session
    session.close()
    trans.rollback()
    connection.close()


@pytest.fixture()
def baza_elektryka_json() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
