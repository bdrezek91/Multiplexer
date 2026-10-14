"""No-network safety tests for Gemini-only production uploads."""
import asyncio
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock,patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from app.modules.documents import router, tasks
from app.modules.ocr.providers import OCRProviderError


def upload():
    return UploadFile(file=BytesIO(b'JPEG-DUMMY'),filename='wydawka.jpg',
                      headers=Headers({'content-type':'image/jpeg'}))


def admin():
    return SimpleNamespace(id=uuid4(),rola='admin')


@pytest.mark.parametrize('engine',['claude_jev_test','standard','unsupported'])
def test_post_rejects_non_gemini_modes_before_saving_files(engine):
    with patch.object(router,'get_storage') as storage:
        with pytest.raises(HTTPException) as error:
            asyncio.run(router.create_document(
                plik=[upload()],magazyn=None,ocr_engine=engine,session=Mock(),user=admin()))
        assert error.value.status_code==422
        storage.assert_not_called()


def test_auto_upload_dispatches_only_primary_ocr_queue():
    expected=SimpleNamespace(id=uuid4(),status='queued')
    storage=Mock()
    session=Mock()
    with patch.object(router,'get_storage',return_value=storage), \
         patch.object(router.repository,'create_document',return_value=expected) as created, \
         patch.object(router,'dispatch_ocr_task') as dispatch:
        result=asyncio.run(router.create_document(
            plik=[upload()],magazyn=None,ocr_engine='auto_v3',session=session,user=admin()))
    assert result.status=='queued'
    assert created.call_args.kwargs['source_type']=='auto_v3'
    dispatch.assert_called_once_with(str(expected.id))


def test_free_gemini_error_never_invokes_claude_or_saves_items():
    doc=SimpleNamespace(id=uuid4(),status='queued',created_at=datetime.now(timezone.utc),
                        file_key='private.jpg',mime='image/jpeg',extra_files=[],magazyn='Zabrze',
                        source_type='auto_v3')
    from app.modules.documents import auto_v3
    with patch.object(tasks.repository,'claim_document_for_processing',return_value=doc), \
         patch.object(tasks.repository,'append_ai_trace_event') as history, \
         patch.object(tasks.repository,'mark_error') as error, \
         patch.object(tasks.repository,'mark_done') as complete, \
         patch.object(tasks.repository,'mark_retry_queued') as requeue, \
         patch.object(tasks.process_ocr_document,'apply_async') as broker, \
         patch.object(tasks,'get_ocr_cooldown_store',return_value=None), \
         patch.object(tasks,'_download_and_prepare',return_value=[(b'IMAGE','image/jpeg')]), \
         patch.object(auto_v3,'recognize_gemini_primary',side_effect=OCRProviderError('429',status_code=429)), \
         patch.object(tasks,'prune_documents'):
        assert tasks.run_ocr_task(str(doc.id),Mock()) is True
    complete.assert_not_called()
    error.assert_not_called()
    requeue.assert_called_once()
    broker.assert_called_once_with(args=[str(doc.id),1],countdown=180,queue='ocr')
    assert any(event.args[2]['stage']=='auto_gemini_primary' and event.args[2]['status']=='failed'
               for event in history.call_args_list)
