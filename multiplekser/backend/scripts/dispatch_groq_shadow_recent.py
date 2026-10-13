"""Zleca Groq shadow dla N najnowszych zakonczonych dokumentow."""
from __future__ import annotations

import argparse

from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.documents.tasks import dispatch_groq_shadow_task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    limit = max(1, min(args.limit, 100))

    session = SessionLocal()
    try:
        docs = (
            session.query(DocumentModel.id)
            .filter(
                DocumentModel.status == "done",
                DocumentModel.dzial.in_(["elektryka", "hydraulika"]),
            )
            .order_by(DocumentModel.created_at.desc())
            .limit(limit)
            .all()
        )
        for (document_id,) in docs:
            dispatch_groq_shadow_task(str(document_id))
        print(f"Zlecono Groq shadow dla {len(docs)} dokumentow.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
