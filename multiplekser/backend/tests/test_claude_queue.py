"""Claude OCR is dispatched to a separate Celery queue, not the Gemini queue."""
from unittest.mock import patch

from app.modules.documents.tasks import (
    dispatch_claude_ocr_task,
    dispatch_ocr_task,
)


def test_claude_dispatch_uses_separate_queue():
    with patch("app.modules.documents.tasks.process_ocr_document.apply_async") as applied:
        dispatch_claude_ocr_task("doc-123")
    applied.assert_called_once_with(args=("doc-123",), queue="claude")


def test_gemini_dispatch_unchanged():
    with patch("app.modules.documents.tasks.process_ocr_document.delay") as delayed:
        dispatch_ocr_task("doc-gemini")
    delayed.assert_called_once_with("doc-gemini")
