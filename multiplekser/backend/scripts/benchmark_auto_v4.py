"""Read-only real-document V4 benchmark. NEVER mutates production documents."""
import argparse
import asyncio
import json
import time
import uuid
from collections import Counter
from pathlib import Path

from sqlalchemy import text
from app.core.db import engine
from app.modules.documents.storage import get_storage
from app.modules.documents.ocr_processing import _download_and_prepare
from app.modules.documents.auto_v4 import shadow_one_pass
from app.modules.products.catalog import plain_norm


def compare(reference, shadow_rows):
    remaining = list(enumerate(shadow_rows))
    pairs=[];missing=[]
    for ref in reference:
        name=plain_norm(ref["rozpoznana_nazwa"])
        matched=next(((i,r) for i,r in remaining if plain_norm(r["nazwa"])==name),None)
        if not matched:
            missing.append(ref["rozpoznana_nazwa"])
            continue
        i,r=matched
        remaining=[(k,v) for k,v in remaining if k!=i]
        qty_ref=(ref["ilosc_wydana"],ref["ilosc_zuzyta"])
        qty_v4=(r.get("ilosc_wydana"),r.get("ilosc_zuzyta"))
        pairs.append((name,qty_ref,qty_v4))
    return {"reference_count":len(reference), "v4_count":len(shadow_rows),
            "names_matched":len(pairs),"qty_exact":sum(a==b for _,a,b in pairs),
            "qty_mismatches":[name for name,a,b in pairs if a!=b][:25],
            "missing_names":missing[:25],
            "extra_names":[r["nazwa"] for _,r in remaining][:25]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--document',default='7dd024c2-1515-4d7b-b6c5-8b2ad74b0cc4')
    p.add_argument('--model',default='gemini-3.5-flash-lite')
    p.add_argument('--thinking',default='minimal')
    p.add_argument('--timeout',type=float,default=27)
    p.add_argument('--page',type=int,default=0,help='1-based single page or 0 for all')
    p.add_argument('--output-dir',default='/tmp',help='secure location for shadow results')
    args=p.parse_args()
    uuid.UUID(args.document)
    with engine.connect() as con:
        doc=con.execute(text('SELECT file_key,mime,status,source_type,dzial,magazyn FROM document WHERE id=:id'),{'id':args.document}).mappings().one()
        refs=[dict(r) for r in con.execute(text('SELECT rozpoznana_nazwa,ilosc_wydana,ilosc_zuzyta,match_kod,match_jm FROM document_item WHERE document_id=:id ORDER BY sequence'),{'id':args.document}).mappings()]
    if doc['status']!='done': raise RuntimeError('Only completed reference documents are permitted')
    prepared_at=time.perf_counter()
    files=_download_and_prepare(get_storage,doc['file_key'],doc['mime'])
    prep_secs=time.perf_counter()-prepared_at
    if args.page:
        files=[files[args.page-1]]
    print('V4_SHADOW_START',args.model,args.thinking,'pages',len(files),'reference',len(refs),'prep_sec',round(prep_secs,2),flush=True)
    started=time.perf_counter()
    try:
        result=asyncio.run(shadow_one_pass(files,model=args.model,thinking=args.thinking,timeout_seconds=args.timeout))
        evaluation=compare(refs,result.rows)
        evaluation.update({'model':args.model,'thinking':args.thinking,'document':args.document,
                           'expected_dzial':doc['dzial'],'classified_dzial':result.dzial,
                           'ocr_sec':result.seconds,'prep_sec':round(prep_secs,3),
                           'invalid_items':result.invalid_count,
                           'input_tokens':result.usage.get('promptTokenCount'),
                           'output_tokens':result.usage.get('candidatesTokenCount'),
                           'thinking_tokens':result.usage.get('thoughtsTokenCount')})
        print('V4_SHADOW_RESULT',json.dumps(evaluation,ensure_ascii=False),flush=True)
        output={'summary':evaluation,'rows':result.rows}
    except Exception as exc:
        evaluation={'model':args.model,'thinking':args.thinking,'document':args.document,
                    'error':type(exc).__name__,'details':str(exc)[:120],
                    'elapsed_sec':round(time.perf_counter()-started,2),'prep_sec':round(prep_secs,3)}
        print('V4_SHADOW_ERROR',json.dumps(evaluation,ensure_ascii=False),flush=True)
        output={'summary':evaluation}
    folder=Path(args.output_dir)
    if not folder.is_dir():
        raise RuntimeError('Shadow output directory must already exist')
    dest=folder/f'auto_v4_{args.document[:8]}_{args.model}_{args.thinking}_p{args.page}_{int(time.time())}.json'
    dest.write_text(json.dumps(output,ensure_ascii=False),encoding='utf-8')
    dest.chmod(0o600)

if __name__=='__main__':main()
