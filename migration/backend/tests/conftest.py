import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_db

# Import jawny (nie poleganie na przypadkowym imporcie z innego pliku testowego) - rejestruje
# wszystkie modele ORM w Base.metadata, zeby Base.metadata.create_all() ponizej zawsze tworzylo
# komplet tabel, niezaleznie od tego, ktore pliki testowe pytest akurat zbiera do uruchomienia.
from app.modules.matcher import models as _matcher_models  # noqa: F401
from app.modules.products import models as _products_models  # noqa: F401
from app.modules.users import models as _users_models  # noqa: F401

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


@pytest.fixture()
def client(db_session):
    """TestClient z Depends(get_db) podmienionym na sesje testowa (rollback po tescie)."""
    from app.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


ADMIN_PASSWORD = "admin-test-haslo-123"
ELEKTRYK_PASSWORD = "elektryk-test-haslo-123"


@pytest.fixture()
def admin_user(db_session):
    from app.modules.users.repository import create_user

    return create_user(db_session, email="admin@test.local", password=ADMIN_PASSWORD, rola="admin")


@pytest.fixture()
def elektryk_user(db_session):
    from app.modules.users.repository import create_user

    return create_user(
        db_session, email="elektryk@test.local", password=ELEKTRYK_PASSWORD,
        rola="elektryk", magazyny_dostepne=["Zabrze"],
    )


def _login_headers(client, email: str, password: str) -> dict[str, str]:
    r = client.post("/auth/token", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client, admin_user):
    return _login_headers(client, admin_user.email, ADMIN_PASSWORD)


@pytest.fixture()
def elektryk_headers(client, elektryk_user):
    return _login_headers(client, elektryk_user.email, ELEKTRYK_PASSWORD)
