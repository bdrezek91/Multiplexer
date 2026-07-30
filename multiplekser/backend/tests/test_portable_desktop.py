"""Testy Multiplekser Portable (patrz docs/RAPORT_PORTABLE_1.md) - trybu desktopowego bez
Dockera/Postgresa/Redis/MinIO. Trzy niezalezne watki:

1. Modele ORM (`Uuid`/`PortableJSON` z app/core/db_types.py) faktycznie dzialaja na SQLite,
   nie tylko kompiluja sie do poprawnego DDL - realny round-trip zapis/odczyt przez wszystkie
   4 modulty (products/users/matcher/documents), zeby wykryc problemy niewidoczne w samym DDL
   (np. serializacja UUID jako obiektu Python, a nie stringa, po stronie SQLAlchemy).
2. `LocalFileStorage` (zamiennik MinIO/S3).
3. `dispatch_ocr_task` faktycznie przelacza sie miedzy Celery (`desktop_mode=False`, domyslne -
   zero zmian dla wdrozenia Docker/produkcyjnego) a watkiem w procesie (`desktop_mode=True`).

Uzywa WLASNEGO silnika SQLite (plik tymczasowy, nie `:memory:` - `:memory:` znika przy
zamknieciu polaczenia, a `dispatch_ocr_task` w trybie desktop otwiera nowa sesje w osobnym
watku) - nie dotyka `db_engine`/`TEST_DATABASE_URL` z conftest.py (te sa Postgresowe, dla
reszty suity).
"""
from __future__ import annotations

import threading
import time
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.db import Base
from app.modules.documents.models import DocumentItemModel, DocumentModel
from app.modules.documents.storage import LocalFileStorage
from app.modules.documents.tasks import dispatch_ocr_task
from app.modules.matcher.models import SpecialRuleModel
from app.modules.products.models import ProductAliasModel, ProductModel, WarehouseVariantModel
from app.modules.users.models import UserModel


@pytest.fixture()
def sqlite_session(tmp_path):
    db_path = tmp_path / "portable_test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True)
    session = SessionLocal()
    yield session
    session.close()
    engine.dispose()


def test_product_z_aliasem_i_wariantem_magazynowym_round_trip_sqlite(sqlite_session):
    product = ProductModel(
        kod="TEST KOD", nazwa="Testowy produkt", dzial="hydraulika",
        atrybuty={"kolor": "bialy", "krotnosc": 2},
    )
    product.aliasy.append(ProductAliasModel(alias_text="alias testowy"))
    product.warianty_magazynowe.append(WarehouseVariantModel(magazyn="Zabrze", kod_docelowy="TEST KOD ZABRZE"))
    sqlite_session.add(product)
    sqlite_session.commit()

    fetched = sqlite_session.query(ProductModel).filter(ProductModel.kod == "TEST KOD").one()
    assert isinstance(fetched.id, uuid.UUID)
    assert fetched.atrybuty == {"kolor": "bialy", "krotnosc": 2}  # PortableJSON round-trip
    assert fetched.aliasy[0].alias_text == "alias testowy"
    assert fetched.warianty_magazynowe[0].kod_docelowy == "TEST KOD ZABRZE"


def test_product_ilike_search_dziala_na_sqlite(sqlite_session):
    sqlite_session.add(ProductModel(kod="A", nazwa="Bezpiecznik 10A", dzial="elektryka"))
    sqlite_session.commit()

    found = sqlite_session.query(ProductModel).filter(ProductModel.nazwa.ilike("%bezpiecznik%")).all()
    assert len(found) == 1


def test_user_magazyny_dostepne_json_round_trip_sqlite(sqlite_session):
    user = UserModel(
        email="portable@test.local", hashed_password="x", rola="elektryk",
        magazyny_dostepne=["Zabrze", "Czekanow"],
    )
    sqlite_session.add(user)
    sqlite_session.commit()

    fetched = sqlite_session.query(UserModel).filter(UserModel.email == "portable@test.local").one()
    assert fetched.magazyny_dostepne == ["Zabrze", "Czekanow"]


def test_special_rule_rounding_steps_json_round_trip_sqlite(sqlite_session):
    rule = SpecialRuleModel(
        rule_type="R3", pattern="szynoprzewod", rounding_steps=[1, 2, 3], priority=1,
    )
    sqlite_session.add(rule)
    sqlite_session.commit()

    fetched = sqlite_session.query(SpecialRuleModel).filter(SpecialRuleModel.rule_type == "R3").one()
    assert fetched.rounding_steps == [1, 2, 3]


def test_document_z_pozycjami_round_trip_sqlite(sqlite_session):
    user = UserModel(email="doc-owner@test.local", hashed_password="x", rola="admin", magazyny_dostepne=[])
    sqlite_session.add(user)
    sqlite_session.commit()

    document = DocumentModel(
        user_id=user.id, file_key="abc.jpg", mime="image/jpeg", original_filename="abc.jpg",
    )
    document.items.append(
        DocumentItemModel(
            sequence=0, rozpoznana_nazwa="Bojler 80 L", match_quality="ok", match_score=1.0,
        )
    )
    sqlite_session.add(document)
    sqlite_session.commit()

    fetched = sqlite_session.query(DocumentModel).filter(DocumentModel.id == document.id).one()
    assert isinstance(fetched.user_id, uuid.UUID)
    assert fetched.user_id == user.id
    assert fetched.items[0].rozpoznana_nazwa == "Bojler 80 L"


def test_local_file_storage_upload_download_round_trip(tmp_path):
    storage = LocalFileStorage(str(tmp_path / "dokumenty"))
    storage.upload("plik.jpg", b"tresc pliku", "image/jpeg")

    assert storage.download("plik.jpg") == b"tresc pliku"


def test_local_file_storage_tworzy_podfoldery_z_klucza(tmp_path):
    """`file_key` zawiera podfoldery (documents/{uuid}/plik.jpg - patrz router.py) - S3 nie ma
    prawdziwych katalogow wiec to bez znaczenia dla S3FileStorage, ale LocalFileStorage musi
    je utworzyc sam, inaczej write_bytes rzuca FileNotFoundError."""
    storage = LocalFileStorage(str(tmp_path / "dokumenty"))
    storage.upload("documents/abc-123/skan.jpg", b"tresc", "image/jpeg")

    assert storage.download("documents/abc-123/skan.jpg") == b"tresc"


def test_local_file_storage_tworzy_folder_jesli_nie_istnieje(tmp_path):
    target = tmp_path / "nieistniejacy" / "podfolder"
    LocalFileStorage(str(target))

    assert target.is_dir()


@pytest.fixture()
def desktop_mode_on():
    original = settings.desktop_mode
    settings.desktop_mode = True
    yield
    settings.desktop_mode = original


def test_dispatch_ocr_task_desktop_mode_uruchamia_w_watku(desktop_mode_on):
    called_with: list[str] = []
    done = threading.Event()

    def fake_run_ocr_task(document_id: str, session) -> None:
        called_with.append(document_id)
        done.set()

    with patch("app.modules.documents.tasks.run_ocr_task", side_effect=fake_run_ocr_task):
        dispatch_ocr_task("some-document-id")
        assert done.wait(timeout=2.0), "run_ocr_task nie zostalo wywolane w watku w ciagu 2s"

    assert called_with == ["some-document-id"]


def test_dispatch_ocr_task_domyslnie_uzywa_celery():
    assert settings.desktop_mode is False  # zalozenie tego testu - domyslna wartosc

    with patch("app.modules.documents.tasks.process_ocr_document.delay") as mock_delay:
        dispatch_ocr_task("some-document-id")

    mock_delay.assert_called_once_with("some-document-id")
