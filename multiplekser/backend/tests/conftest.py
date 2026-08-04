import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import Base, get_db

# Import jawny (nie poleganie na przypadkowym imporcie z innego pliku testowego) - rejestruje
# wszystkie modele ORM w Base.metadata, zeby Base.metadata.create_all() ponizej zawsze tworzylo
# komplet tabel, niezaleznie od tego, ktore pliki testowe pytest akurat zbiera do uruchomienia.
from app.modules.matcher import models as _matcher_models  # noqa: F401
from app.modules.products import models as _products_models  # noqa: F401
from app.modules.users import models as _users_models  # noqa: F401
from app.modules.documents import models as _documents_models  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://multiplekser:multiplekser_dev@localhost:5432/multiplekser_test",
)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "baza_elektryka.json"
_HYDRAULIKA_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "baza_hydraulika.json"


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
def baza_hydraulika_json() -> dict:
    return json.loads(_HYDRAULIKA_FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Rate limiting na /auth/token (Etap "quick winy") liczy proby w Redis per-IP, wspolnym
    dla calego procesu testowego - bez resetu przed kazdym testem setki logowan przez fixture
    `admin_headers`/`magazynier_headers` (kazdy test loguje sie od nowa) szybko wyczerpalyby limit
    "5/minute" i posypaly niepowiazane testy 429-kami zamiast prawdziwych bledow."""
    from app.core.rate_limit import limiter

    limiter.reset()
    yield


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
MAGAZYNIER_PASSWORD = "magazynier-test-haslo-123"


@pytest.fixture()
def admin_user(db_session):
    from app.modules.users.repository import create_user

    return create_user(db_session, email="admin@test.local", password=ADMIN_PASSWORD, rola="admin")


@pytest.fixture()
def magazynier_user(db_session):
    from app.modules.users.repository import create_user

    return create_user(
        db_session, email="magazynier@test.local", password=MAGAZYNIER_PASSWORD,
        rola="magazynier", magazyny_dostepne=["Zabrze"],
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
def magazynier_headers(client, magazynier_user):
    return _login_headers(client, magazynier_user.email, MAGAZYNIER_PASSWORD)


@pytest.fixture()
def gemini_key_configured():
    original = settings.gemini_api_key_free
    settings.gemini_api_key_free = "test-key"
    yield
    settings.gemini_api_key_free = original


@pytest.fixture()
def openai_key_configured():
    """Wlacza cross-check OpenAI (patrz ocr/crosscheck.py) - domyslnie WYLACZONY w testach
    (settings.openai_api_key=None), tak jak w produkcji bez skonfigurowanego klucza."""
    original = settings.openai_api_key
    settings.openai_api_key = "test-openai-key"
    yield
    settings.openai_api_key = original


@pytest.fixture()
def mocked_storage():
    """S3/MinIO zamockowane przez moto - endpoint_url musi byc None (moto przechwytuje tylko
    ruch do rozpoznawanych endpointow AWS, nie do dowolnego custom URL jak prawdziwy MinIO)."""
    original_endpoint = settings.minio_endpoint_url
    settings.minio_endpoint_url = None
    with mock_aws():
        yield
    settings.minio_endpoint_url = original_endpoint
