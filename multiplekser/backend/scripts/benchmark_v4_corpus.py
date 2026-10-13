"""Read-only geometry candidate coverage across independent document layouts (non-GOLD)."""
import argparse
import difflib
import json
from pathlib import Path
from app.modules.documents.auto_v4_geometry import blue_rows
from app.modules.products.catalog import plain_norm


def coverage(refs, candidates):
    pool=[plain_norm(c.name) for c in candidates]
    exact=fuzzy=0;missed=[]
    for label in refs:
        n=plain_norm(label)
        if n in pool:
            exact+=1;pool.remove(n);continue
        best=sorted(((difflib.SequenceMatcher(None,n,k).ratio(),k) for k in pool),reverse=True)
        if best and best[0][0]>=.83:
            fuzzy+=1;pool.remove(best[0][1]);continue
        missed.append(label)
    return {'matched':exact+fuzzy,'exact':exact,'missed':len(missed),'extra':len(pool),'missing_names':missed[:10]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--folder',default='/private')
    args=parser.parse_args();path=Path(args.folder)
    for doc in ('elektr','hyd'):
        meta=json.loads((path/f'{doc}_meta.json').read_text(encoding='utf-8'))
        pages=[]
        for p in range(1,meta['pages']+1):
            image=(path/f'{doc}{p}.jpg').read_bytes()
            ocr=json.loads((path/f'{doc}{p}_ocr.json').read_text(encoding='utf-8'))['lines']
            try:
                candidates=blue_rows(image,ocr,page=p)
            except Exception as exc:
                print('FORM_UNSUPPORTED',doc,'page',p,type(exc).__name__,str(exc)[:75],flush=True)
                break
            pages.extend(candidates)
            print('PAGE',doc,p,'labels',len(candidates),'blue_candidates_20',sum(x.marked for x in candidates),flush=True)
        if len(pages)==0:continue
        for t in (20,50,70,90,110,140):
            candidates=[r for r in pages if max(r.issued_blue_pixels,r.consumed_blue_pixels)>=t]
            print('CORPUS',doc,'threshold',t,'ref',len(meta['reference']),'candidates',len(candidates),
                  'coverage',coverage(meta['reference'],candidates),flush=True)

if __name__=='__main__':main()
