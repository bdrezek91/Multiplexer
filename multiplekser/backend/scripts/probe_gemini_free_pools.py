"""Manual no-write real OCR probe: compare a FREE Gemini pool to saved document rows.

Usage: python -m scripts.probe_gemini_free_pools --pool FREE2 --model gemini-3.6-flash
Never exposes keys, raw customer documents, prompts, or OCR responses to stdout.
"""
import argparse
import asyncio
from collections import Counter
from decimal import Decimal, InvalidOperation
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
    p.add_argument('--pool',choices=('FREE1','FREE2','BOTH'),required=True)
    p.add_argument('--model',choices=('auto','gemini-3.5-flash-lite','gemini-3.6-flash','gemini-3.1-flash-lite'),
                   default='auto')
    p.add_argument('--document',default='4e1c0ac0-dc17-406e-9cea-38f07e4fc9cb')
    args=p.parse_args()
    if args.pool=='FREE1':
        settings.gemini_api_key_free_2=None
        if not settings.gemini_api_key_free: raise RuntimeError('FREE1 not configured')
    elif args.pool=='FREE2':
        settings.gemini_api_key_free=None
        if not settings.gemini_api_key_free_2: raise RuntimeError('FREE2 not configured')
    else:
        if not (settings.gemini_api_key_free and settings.gemini_api_key_free_2):
            raise RuntimeError('Both free projects must be configured')
    # No paid key may ever be used in this script.
    settings.gemini_api_key_paid=None
    with SessionLocal() as session:
        doc=session.execute(text('SELECT file_key,mime,status,dzial FROM document WHERE id=:id'),
                            {'id':args.document}).mappings().one()
        if doc['status']!='done': raise RuntimeError('Completed reference required')
        ref_items=session.execute(text('SELECT rozpoznana_nazwa,ilosc_wydana,ilosc_zuzyta FROM document_item '
                    'WHERE document_id=:id ORDER BY sequence'),{'id':args.document}).all()
        refs=[r[0] for r in ref_items]
        t=time.perf_counter()
        files=_download_and_prepare(get_storage,doc['file_key'],doc['mime'])
        prep=round(time.perf_counter()-t,3)
        started=time.perf_counter()
        print('OCR_PROBE_START',args.pool,args.model,'pages',len(files),
              'reference_rows',len(refs),'prep_seconds',prep,flush=True)
        events=[]
        try:
            classification,dzial,result,timings=recognize_gemini_primary(
                files,session,magazyn='Zabrze',model=None if args.model=='auto' else args.model,
                cooldown_store=None,event_callback=events.append)
            elapsed=round(time.perf_counter()-started,3)
            original=Counter(plain_norm(x) for x in refs)
            observed=Counter(plain_norm(x.rozpoznana_nazwa) for x in result.pozycje)
            same=sum((original&observed).values())
            def number(v):
                if v is None or str(v).strip()=='': return None
                try: return Decimal(str(v).replace(',','.'))
                except (InvalidOperation,ValueError): return 'NONNUMERIC'
            original_pairs=Counter((plain_norm(n),number(w),number(u)) for n,w,u in ref_items)
            extracted_pairs=Counter((plain_norm(x.rozpoznana_nazwa),
                                     number(getattr(x,'ilosc_wydana',None)),
                                     number(getattr(x,'ilosc_zuzyta',None))) for x in result.pozycje)
            pair_matches=sum((original_pairs&extracted_pairs).values())
            print('OCR_PROBE_RESULT','pool',args.pool,'model',args.model,
                  'seconds',elapsed,'page_prepare_seconds',prep,
                  'department_correct',dzial==doc['dzial'],
                  'reference_rows',len(refs),'candidate_rows',len(result.pozycje),
                  'exact_name_matches',same,'name_and_quantity_pairs_matched',pair_matches,
                  'quantity_disagreements_or_missing_pairs',len(ref_items)-pair_matches,
                  'extra_candidates',sum((observed-original).values()),
                  'unmatched_references',sum((original-observed).values()),
                  'classification_seconds',timings.get('timing_classification',0)/1000,
                  'ocr_and_match_seconds',timings.get('timing_ocr_matcher',0)/1000,
                  'events',[(x.get('stage'),x.get('label'),x.get('status'),x.get('duration_ms')) for x in events[-12:]],
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
