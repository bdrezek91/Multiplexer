"""Read-only V4 geometry coverage vs non-GOLD production labels.

Uses ephemeral prepared images and RapidOCR result JSON supplied as CLI arguments;
never changes document data. Review apparent false positives against source scans.
"""
import argparse
import difflib
import json
from collections import Counter
from pathlib import Path
from sqlalchemy import text
from app.core.db import engine
from app.modules.products.catalog import plain_norm
from app.modules.documents.auto_v4_geometry import blue_rows


def compare(labels, candidates):
    remaining=list(candidates)
    exact=[];fuzzy=[];missing=[]
    for label in labels:
        norm=plain_norm(label)
        m=next((v for v in remaining if plain_norm(v.name)==norm),None)
        if m is not None:
            exact.append((label,m.name));remaining.remove(m);continue
        matches=sorted(((difflib.SequenceMatcher(None,norm,plain_norm(v.name)).ratio(),v) for v in remaining),key=lambda x:x[0],reverse=True)
        if matches and matches[0][0]>=.83:
            fuzzy.append((label,matches[0][1].name,round(matches[0][0],2)))
            remaining.remove(matches[0][1]);continue
        missing.append(label)
    return {'production_rows':len(labels),'ink_candidates':len(candidates),'exact_names':len(exact),
            'fuzzy_names':len(fuzzy),'missed_vs_stored':len(missing),'possible_extra':len(remaining),
            'fuzzy_details':fuzzy[:15],'missed_names':missing[:18],
            'extra_candidates':[x.name for x in remaining][:18]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--document',required=True,help='Completed document ID')
    p.add_argument('--image-prefix',default='/tmp/v4page')
    p.add_argument('--ocr-prefix',default='/tmp/cpu_page')
    a=p.parse_args()
    labels=[]
    with engine.connect() as c:
        labels=[r[0] for r in c.execute(text('SELECT rozpoznana_nazwa FROM document_item WHERE document_id=:id ORDER BY sequence'),{'id':a.document})]
    items=[]
    for page in range(1,4):
        im=Path(f'{a.image_prefix}{page}.jpg').read_bytes()
        rows=json.loads(Path(f'{a.ocr_prefix}{page}.json').read_text(encoding='utf-8'))['lines']
        candidates=blue_rows(im,rows,page=page)
        marked=[v for v in candidates if v.marked]
        print('PAGE',page,'form_labels',len(candidates),'ink_candidates',len(marked),flush=True)
        items+=marked
    print('COVERAGE_NON_GOLD',json.dumps(compare(labels,items),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
