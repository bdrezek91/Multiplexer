"""Shadow-only concurrent 3-page V4 benchmark. Never mutates production tables."""
import argparse
import asyncio
import json
import time
from sqlalchemy import text
from app.core.db import engine
from app.modules.documents.storage import get_storage
from app.modules.documents.ocr_processing import _download_and_prepare
from app.modules.documents.auto_v4 import shadow_one_pass
from scripts.benchmark_auto_v4 import compare

DOC='7dd024c2-1515-4d7b-b6c5-8b2ad74b0cc4'

async def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',default='gemini-3.6-flash')
    p.add_argument('--thinking',default='minimal')
    p.add_argument('--timeout',type=float,default=22)
    args=p.parse_args()
    with engine.connect() as con:
        row=con.execute(text('SELECT file_key,mime,status,dzial FROM document WHERE id=:id'),{'id':DOC}).mappings().one()
        ref=[dict(r) for r in con.execute(text('SELECT rozpoznana_nazwa,ilosc_wydana,ilosc_zuzyta FROM document_item WHERE document_id=:id ORDER BY sequence'),{'id':DOC}).mappings()]
    assert row['status']=='done'
    t=time.perf_counter()
    files=_download_and_prepare(get_storage,row['file_key'],row['mime'])
    prep=time.perf_counter()-t
    print('V4_PARALLEL_START','pages',len(files),'prep',round(prep,2),flush=True)
    start=time.perf_counter()
    outcomes=await asyncio.gather(*[
        shadow_one_pass([file],model=args.model,thinking=args.thinking,timeout_seconds=args.timeout)
        for file in files
    ],return_exceptions=True)
    ocr=time.perf_counter()-start
    combined=[];page_info=[]
    for i,result in enumerate(outcomes):
        if isinstance(result,Exception):
            page_info.append({'page':i+1,'error':type(result).__name__,'detail':str(result)[:140]})
            continue
        page_info.append({'page':i+1,'count':len(result.rows),'duration':result.seconds,
                          'input_tokens':result.usage.get('promptTokenCount'),
                          'output_tokens':result.usage.get('candidatesTokenCount'),
                          'dzial':result.dzial})
        for row in result.rows:
            row['strona']=i+1
            combined.append(row)
    complete=len(combined)>0 and all('error' not in v for v in page_info)
    # Never score a PARTIAL OCR against a FULL reference as if it were a miss.
    metrics=compare(ref,combined) if complete else {
        'comparison_scope':'incomplete_unscored',
        'reason':'At least one page did not return a usable OCR result',
        'reference_total_all_pages':len(ref),
        'returned_partial_rows':len(combined)}
    metrics.update({'ocr_wall_sec':round(ocr,3),'prep_sec':round(prep,3),
                    'total_without_jev':round(ocr+prep,3),'all_pages_ok':complete,
                    'review_flags':sum(len(p.review_flags) for p in outcomes if not isinstance(p,Exception)),
                    'pages':page_info})
    print('V4_PARALLEL_RESULT',json.dumps(metrics,ensure_ascii=False),flush=True)

if __name__=='__main__':asyncio.run(main())
