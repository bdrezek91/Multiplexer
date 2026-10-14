"""Regression gates for safe auto retries; no Google API, documents or production database touched."""
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import Mock,patch
from uuid import uuid4
import asyncio
import pytest
from app.modules.documents import tasks, repository
from app.modules.documents import auto_v3
from app.modules.ocr.chain import OCRChainStep,run_ocr_chain
from app.modules.ocr.providers import OCRProviderError


def _fake_document():
    return SimpleNamespace(id=uuid4(),status='queued',created_at=datetime.now(timezone.utc),
             file_key='sample.pdf',mime='application/pdf',extra_files=[],magazyn='Zabrze',
             source_type='auto_v3',ai_trace=[])


@pytest.mark.parametrize('attempt,delay',[(0,180),(1,900)])
def test_retries_same_doc_after_free_gemini_unavailable_no_early_error(attempt,delay):
    d=_fake_document()
    with patch.object(tasks.repository,'claim_document_for_processing',return_value=d), \
         patch.object(tasks.repository,'append_ai_trace_event'), \
         patch.object(tasks.repository,'mark_error') as mark_error, \
         patch.object(tasks.repository,'mark_done') as mark_done, \
         patch.object(tasks.repository,'mark_retry_queued') as requeue, \
         patch.object(tasks.process_ocr_document,'apply_async') as enqueue, \
         patch.object(tasks,'get_ocr_cooldown_store',return_value=None), \
         patch.object(tasks,'_download_and_prepare',return_value=[(b'SCAN','image/jpeg')]), \
         patch.object(auto_v3,'recognize_gemini_primary',side_effect=OCRProviderError('429',status_code=429)), \
         patch.object(tasks,'prune_documents'):
        assert tasks.run_ocr_task(str(d.id),Mock(),retry_attempt=attempt) is True
    mark_error.assert_not_called()
    mark_done.assert_not_called()
    requeue.assert_called_once()
    assert requeue.call_args.kwargs=={'retry_number':attempt+1,'countdown_seconds':delay}
    enqueue.assert_called_once_with(args=[str(d.id),attempt+1],countdown=delay,queue='ocr')


def test_after_3_attempts_ends_as_reviewable_error_not_infinite_loop():
    d=_fake_document()
    with patch.object(tasks.repository,'claim_document_for_processing',return_value=d), \
         patch.object(tasks.repository,'append_ai_trace_event'), \
         patch.object(tasks.repository,'mark_error') as error, \
         patch.object(tasks.repository,'mark_done') as done, \
         patch.object(tasks.repository,'mark_retry_queued') as requeue, \
         patch.object(tasks.process_ocr_document,'apply_async') as enqueue, \
         patch.object(tasks,'get_ocr_cooldown_store',return_value=None), \
         patch.object(tasks,'_download_and_prepare',return_value=[(b'SCAN','image/jpeg')]), \
         patch.object(auto_v3,'recognize_gemini_primary',side_effect=OCRProviderError('429',status_code=429)), \
         patch.object(tasks,'prune_documents'):
        assert tasks.run_ocr_task(str(d.id),Mock(),retry_attempt=2) is True
    done.assert_not_called();enqueue.assert_not_called();requeue.assert_not_called()
    assert '3 próbach' in error.call_args.args[2]


def test_queue_publish_failure_marks_error_not_stuck_in_queued():
    d=_fake_document()
    with patch.object(tasks.repository,'claim_document_for_processing',return_value=d), \
         patch.object(tasks.repository,'append_ai_trace_event'), \
         patch.object(tasks.repository,'mark_error') as error, \
         patch.object(tasks.repository,'mark_retry_queued'), \
         patch.object(tasks.process_ocr_document,'apply_async',side_effect=RuntimeError('broken redis')), \
         patch.object(tasks,'get_ocr_cooldown_store',return_value=None), \
         patch.object(tasks,'_download_and_prepare',return_value=[(b'SCAN','image/jpeg')]), \
         patch.object(auto_v3,'recognize_gemini_primary',side_effect=OCRProviderError('429',status_code=429)), \
         patch.object(tasks,'prune_documents'):
        assert tasks.run_ocr_task(str(d.id),Mock(),retry_attempt=0) is True
    assert 'nie udało się zaplanować' in error.call_args.args[2]


def test_invalid_department_is_not_retried_as_quota_failure():
    d=_fake_document()
    with patch.object(tasks.repository,'claim_document_for_processing',return_value=d), \
         patch.object(tasks.repository,'append_ai_trace_event'), \
         patch.object(tasks.repository,'mark_error') as error, \
         patch.object(tasks.repository,'mark_retry_queued') as requeue, \
         patch.object(tasks.process_ocr_document,'apply_async') as enqueue, \
         patch.object(tasks,'get_ocr_cooldown_store',return_value=None), \
         patch.object(tasks,'_download_and_prepare',return_value=[(b'SCAN','image/jpeg')]), \
         patch.object(auto_v3,'recognize_gemini_primary',side_effect=ValueError('invalid department')), \
         patch.object(tasks,'prune_documents'):
        tasks.run_ocr_task(str(d.id),Mock())
    error.assert_called_once();requeue.assert_not_called();enqueue.assert_not_called()


class Cooldown:
    def __init__(self):self.ttls={}
    def remaining_seconds(self,label):return self.ttls.get(label,0)
    def record_timeout(self,label):self.ttls[label]=120;return 2
    def reset(self,label):pass


class Provider:
    def __init__(self):self.calls=[]
    async def recognize(self,*,files,model,api_key,prompt,thinking_level='low'):
        self.calls.append(api_key)
        if prompt=='classification':await asyncio.sleep(.05)
        return 'valid OCR'


def test_header_timeout_does_not_block_same_model_for_full_ocr():
    p=Provider();c=Cooldown();step=OCRChainStep('Gemini 3.5 FREE2',p,'gemini-3.5-flash-lite','KEY',.01)
    with pytest.raises(Exception):
        asyncio.run(run_ocr_chain([(b'page','image/jpeg')],'classification',chain=[step],
                    log_context={'ai_stage':'classification'},cooldown_store=c))
    assert c.remaining_seconds(step.label)==0
    assert c.remaining_seconds(step.label+'|timeout|classification')==120
    full=OCRChainStep(step.label,p,step.model,'KEY',.2)
    result=asyncio.run(run_ocr_chain([(b'page','image/jpeg')],'full',chain=[full],
                      log_context={'ai_stage':'full_ocr_elektryka'},cooldown_store=c))
    assert result.text=='valid OCR'


def test_claim_for_retry_preserves_previous_ai_events():
    session=Mock()
    session.query.return_value.filter.return_value.update.return_value=1
    doc=_fake_document()
    with patch.object(repository,'get_document',return_value=doc):
        assert repository.claim_document_for_processing(session,str(doc.id)) is doc
    values=session.query.return_value.filter.return_value.update.call_args.args[0]
    assert len(values)==1
    assert next(iter(values.values()))=='processing'


def test_retry_metadata_same_document_and_preserved_history():
    doc=_fake_document();doc.ai_trace=[{'status':'rejected','stage':'classification'}]
    session=Mock()
    repository.mark_retry_queued(session,doc,retry_number=1,countdown_seconds=180)
    assert doc.status=='queued' and doc.error_message is None
    assert doc.ai_trace[0]['status']=='rejected'
    assert doc.ai_trace[-1]['stage']=='gemini_retry'
    assert doc.ai_trace[-1]['attempt']==2
    session.commit.assert_called_once()
