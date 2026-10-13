"""Read-only threshold curves against production (not GOLD), no silent acceptance."""
import argparse
import difflib
import json
from pathlib import Path
from sqlalchemy import text
from app.core.db import engine
from app.modules.products.catalog import plain_norm
from app.modules.documents.auto_v4_geometry import blue_rows


def assess(baseline, candidates):
    names=[plain_norm(r.name) for r in candidates]
    remain=names.copy();exact=fuzzy=0;missed=[]
    for raw in baseline:
        normalized=plain_norm(raw)
        if normalized in remain:
            exact+=1;remain.remove(normalized);continue
        sim=[(difflib.SequenceMatcher(None,normalized,n).ratio(),n) for n in remain]
        if sim and max(sim)[0]>=.83:
            fuzzy+=1;remain.remove(max(sim)[1]);continue
        missed.append(raw)
    return {'exact':exact,'fuzzy':fuzzy,'missed':len(missed),'extras':len(remain),'missed_examples':missed[:8]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--document',required=True,help='Completed document ID')
    p.add_argument('--folder',default='/private')
    a=p.parse_args();folder=Path(a.folder)
    with engine.connect() as c:
        refs=[r[0] for r in c.execute(text('SELECT rozpoznana_nazwa FROM document_item WHERE document_id=:id ORDER BY sequence'),{'id':a.document})]
    pages=[]
    for n in (1,2,3):
        img=(folder/f'page{n}.jpg').read_bytes()
        lines=json.loads((folder/f'cpu_page{n}.json').read_text(encoding='utf-8'))['lines']
        pages.append(blue_rows(img,lines,page=n))
    print('REFERENCE',len(refs),'CANDIDATES',sum(map(len,pages)),flush=True)
    for t in (10,20,30,40,50,70,90,110,140,200,260):
        selected=[r for page in pages for r in page if max(r.issued_blue_pixels,r.consumed_blue_pixels)>=t]
        result=assess(refs,selected)
        print('THRESHOLD',t,'CANDIDATES',len(selected),'EXACT',result['exact'],'FUZZY',result['fuzzy'],'MISSING',result['missed'],'EXTRA',result['extras'],'missing_names',result['missed_examples'],flush=True)

if __name__=='__main__':main()
