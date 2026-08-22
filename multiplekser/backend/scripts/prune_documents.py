"""Usuwa stare zakonczone analizy zgodnie z DOCUMENT_RETENTION_LIMIT.

Uzycie produkcyjne:
    python -m scripts.prune_documents
"""
from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.documents.retention import prune_documents
from app.modules.documents.storage import get_storage


def main() -> None:
    session = SessionLocal()
    try:
        removed = prune_documents(session, get_storage(), limit=settings.document_retention_limit)
        print(f"Usunieto {removed} starych analiz; limit={settings.document_retention_limit}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
