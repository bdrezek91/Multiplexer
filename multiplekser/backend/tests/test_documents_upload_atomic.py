"""Atomowosc wielostronicowego uploadu bez zaleznosci od Postgresa/S3."""
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.modules.documents.router import create_document


class _Upload:
    def __init__(self, filename: str, data: bytes, content_type: str = "image/jpeg"):
        self.filename = filename
        self._data = data
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._data


class _Session:
    def __init__(self):
        self.rolled_back = 0
        self.deleted = []
        self.committed = 0

    def rollback(self):
        self.rolled_back += 1

    def delete(self, value):
        self.deleted.append(value)

    def commit(self):
        self.committed += 1


class _Storage:
    def __init__(self, fail_on_upload: int | None = None):
        self.fail_on_upload = fail_on_upload
        self.uploaded: list[str] = []
        self.deleted: list[str] = []

    def upload(self, key: str, data: bytes, content_type: str):
        attempt = len(self.uploaded) + 1
        if attempt == self.fail_on_upload:
            raise RuntimeError("storage failure")
        self.uploaded.append(key)

    def delete(self, key: str):
        self.deleted.append(key)


async def test_blad_drugiego_uploadu_usuwa_pierwszy_obiekt():
    storage = _Storage(fail_on_upload=2)
    session = _Session()
    user = SimpleNamespace(id=uuid.uuid4(), rola="admin")

    with (
        patch("app.modules.documents.router.get_storage", return_value=storage),
        patch("app.modules.documents.router.repository.create_document") as create_row,
    ):
        with pytest.raises(RuntimeError, match="storage failure"):
            await create_document(
                [_Upload("strona1.jpg", b"pierwsza"), _Upload("strona2.jpg", b"druga")],
                None, session, user,
            )

    assert len(storage.uploaded) == 1
    assert storage.deleted == storage.uploaded
    assert session.rolled_back == 1
    create_row.assert_not_called()


async def test_pusta_druga_strona_jest_odrzucona_przed_pierwszym_uploadem():
    session = _Session()
    user = SimpleNamespace(id=uuid.uuid4(), rola="admin")

    with patch("app.modules.documents.router.get_storage") as get_storage:
        with pytest.raises(HTTPException) as exc_info:
            await create_document(
                [_Upload("strona1.jpg", b"pierwsza"), _Upload("strona2.jpg", b"")],
                None, session, user,
            )

    assert exc_info.value.status_code == 400
    get_storage.assert_not_called()


async def test_blad_zlecenia_ocr_usuwa_rekord_i_wszystkie_pliki():
    storage = _Storage()
    session = _Session()
    user = SimpleNamespace(id=uuid.uuid4(), rola="admin")
    document = SimpleNamespace(id=uuid.uuid4(), status="queued")

    with (
        patch("app.modules.documents.router.get_storage", return_value=storage),
        patch("app.modules.documents.router.repository.create_document", return_value=document),
        patch("app.modules.documents.router.dispatch_ocr_task", side_effect=RuntimeError("queue failure")),
    ):
        with pytest.raises(RuntimeError, match="queue failure"):
            await create_document(
                [_Upload("strona1.jpg", b"pierwsza"), _Upload("strona2.jpg", b"druga")],
                None, session, user,
            )

    assert session.deleted == [document]
    assert session.committed == 1
    assert storage.deleted == list(reversed(storage.uploaded))
