"""Manual no-write real OCR probe: compare a FREE Gemini pool to saved document rows.

Usage: python -m scripts.probe_gemini_free_pools --pool FREE2 --model gemini-3.6-flash
Never exposes keys, raw customer documents, prompts, or OCR responses to stdout.
"""
import argparse
import asyncio
from collections import Counter
import time

from sqlalchemy import text
from app.core.config import settings
from app.core.db import SessionLocal
# Register ORM relationships before Catalog.from_db; production imports this via tasks.
from app.modules.documents import repository as _document_models_registered
from app.modules.documents.storage import get_storage
from app.modules.documents.ocr_processing import _download_and_prepare
from app.modules.documents.auto_v3 import recognize_gemini_primary
from app.modules.products.catalog import plain_norm


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pool',choices=('FREE1','FREE2'),required=True)
    p.add_argument('--model',choices=('gemini-3.5-flash-lite','gemini-3.6-flash','gemini-3.1-flash-lite'),
                   default='gemini-3.6-flash')
    p.add_argument('--document',default='4e1c0ac0-dc17-406e-9cea-38f07e4fc9cb')
    args=p.parse_args()
    if args.pool=='FREE1':
        settings.gemini_api_key_free_2=None
        if not settings.gemini_api_key_free: raise RuntimeError('FREE1 not configured')
    else:
        settings.gemini_api_key_free=None
        if not settings.gemini_api_key_free_2: raise RuntimeError('FREE2 not configured')
    # No paid key may ever be used in this script.
    settings.gemini_api_key_paid=None
    with SessionLocal() as session:
        doc=session.execute(text('SELECT file_key,mime,status,dzial FROM document WHERE id=:id'),
                            {'id':args.document}).mappings().one()
        if doc['status']!='done': raise RuntimeError('Completed reference required')
        refs=[r[0] for r in session.execute(text('SELECT rozpoznana_nazwa FROM document_item '
                    'WHERE document_id=:id ORDER BY sequence'),{'id':args.document})]
        t=time.perf_counter()
        files=_download_and_prepare(get_storage,doc['file_key'],doc['mime'])
        prep=round(time.perf_counter()-t,3)
        started=time.perf_counter()
        print('OCR_PROBE_START',args.pool,args.model,'pages',len(files),
              'reference_rows',len(refs),'prep_seconds',prep,flush=True)
        events=[]
        try:
            classification,dzial,result,timings=recognize_gemini_primary(
                files,session,magazyn='Zabrze',model=args.model,
                cooldown_store=None,event_callback=events.append)
            elapsed=round(time.perf_counter()-started,3)
            original=Counter(plain_norm(x) for x in refs)
            observed=Counter(plain_norm(x.rozpoznana_nazwa) for x in result.pozycje)
            same=sum((original&observed).values())
            print('OCR_PROBE_RESULT','pool',args.pool,'model',args.model,
                  'seconds',elapsed,'page_prepare_seconds',prep,
                  'department_correct',dzial==doc['dzial'],
                  'reference_rows',len(refs),'candidate_rows',len(result.pozycje),
                  'exact_name_matches',same,'extra_candidates',sum((observed-original).values()),
                  'unmatched_references',sum((original-observed).values()),
                  'classification_seconds',timings.get('timing_classification',0)/1000,
                  'ocr_and_match_seconds',timings.get('timing_ocr_matcher',0)/1000,
                  flush=True)
        except Exception as exc:
            import traceback
            frames=traceback.extract_tb(exc.__traceback__)
            print('OCR_PROBE_ERROR','pool',args.pool,'model',args.model,
                  'error_type',type(exc).__module__+'.'+type(exc).__name__,
                  'origin',[(frame.filename.rsplit('/',1)[-1],frame.lineno) for frame in frames[-4:]],
                  'cause_type',type(getattr(exc,'last_error',None)).__name__,
                  'cause_http',getattr(getattr(exc,'last_error',None),'status_code',None),
                  'events',[(x.get('stage'),x.get('label'),x.get('status')) for x in events[-8:]],
                  'elapsed_seconds',round(time.perf_counter()-started,3),flush=True)

if __name__=='__main__':main()
