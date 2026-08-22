from datetime import datetime, timedelta, timezone

from app.modules.documents import repository
from app.modules.documents.models import DocumentModel
from app.modules.documents.retention import prune_documents
from app.modules.documents.storage import get_storage


def test_retention_keeps_latest_20_and_protects_processing(
    db_session, admin_user, mocked_storage,
):
    storage = get_storage()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    documents = []

    for index in range(24):
        key = f"documents/retention/{index:03d}.jpg"
        storage.upload(key, f"file-{index}".encode(), "image/jpeg")
        document = repository.create_document(
            db_session,
            user_id=admin_user.id,
            file_key=key,
            mime="image/jpeg",
            original_filename=f"{index:03d}.jpg",
        )
        document.created_at = base + timedelta(minutes=index)
        document.status = "processing" if index == 0 else "done"
        db_session.commit()
        documents.append(document)

    removed = prune_documents(db_session, storage, limit=20)

    assert removed == 3
    assert db_session.query(DocumentModel).count() == 21
    assert repository.get_document(db_session, documents[0].id).status == "processing"
    assert repository.get_document(db_session, documents[1].id) is None
    assert repository.get_document(db_session, documents[2].id) is None
    assert repository.get_document(db_session, documents[3].id) is None
    assert repository.get_document(db_session, documents[4].id) is not None
