"""Export one page of a completed document for private, temporary Claude OCR benchmarking."""
from pathlib import Path
from app.modules.documents.tasks import dispatch_groq_shadow_task
from app.core.db import SessionLocal
from app.modules.documents.models import DocumentModel
from app.modules.documents.ocr_processing import _download_and_prepare
from app.modules.documents.storage import get_storage

db = SessionLocal()
try:
    doc = db.query(DocumentModel).filter(
        DocumentModel.status == "done",
        DocumentModel.dzial == "hydraulika",
    ).order_by(DocumentModel.created_at.desc()).first()
    if not doc:
        raise SystemExit("NO_DOCUMENT")
    pages = _download_and_prepare(get_storage, doc.file_key, doc.mime)
    image, mime = pages[0]
    path = Path("/tmp/claude_ocr_shadow_page1.jpg")
    path.write_bytes(image)
    path.chmod(0o600)
    print("EXPORTED", len(image), mime, "PAGES", len(pages), "REF_ITEMS", len(doc.items))
finally:
    db.close()
