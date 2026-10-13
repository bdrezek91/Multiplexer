"""Reczne zlecenie JEDNEGO dokumentu do Cloudflare Gemma shadow OCR.

Nie modyfikuje TXT ani wyniku produkcyjnego. Uzywa istniejacego dokumentu done.
"""
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.documents.tasks import dispatch_cloudflare_shadow_task


def main():
    db = SessionLocal()
    try:
        doc = (
            db.query(DocumentModel.id, DocumentModel.dzial)
            .filter(
                DocumentModel.status == "done",
                DocumentModel.dzial.in_(["elektryka", "hydraulika"]),
            )
            .order_by(DocumentModel.created_at.desc())
            .first()
        )
        if doc is None:
            print("BRAK zakonczonych dokumentow testowych")
            return
        dispatch_cloudflare_shadow_task(str(doc[0]))
        print(f"Cloudflare shadow: zlecono jeden dokument {doc[0]} ({doc[1]})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
