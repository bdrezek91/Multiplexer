"""Read-only electrical dark-ink presence detector, independent from OCR digit recognition."""
import argparse
import difflib
import json
from pathlib import Path
import cv2
import numpy as np
from app.modules.documents.auto_v4_electric import calibrate_electric,center,normalized
from app.modules.products.catalog import plain_norm


def detect(img,lines,calibration,*,has_header):
    gray=cv2.imdecode(np.frombuffer(img,dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
    start=calibration.header_y+27 if has_header else 110
    rows=[]
    for line in lines:
        try:x,y=center(line)
        except (TypeError,ValueError,IndexError):continue
        name=str(line.get('text') or '').strip()
        if x>calibration.issued_x-110 or y<start or len(name)<4:continue
        if normalized(name) in {'inne:', 'nazwa'}:continue
        cy=round(y)
        def presence(center_x):
            left=max(0,round(center_x)-62);right=min(gray.shape[1],round(center_x)+62)
            yy0=max(0,cy-11); yy1=min(gray.shape[0],cy+12)
            return int(np.count_nonzero(gray[yy0:yy1,left:right]<120))
        rows.append((name,presence(calibration.issued_x),presence(calibration.used_x)))
    return rows


def score(refs,selected):
    remaining=[plain_norm(x[0]) for x in selected]
    exact=fuzzy=0;missing=[]
    for row in refs:
        name=plain_norm(row)
        if name in remaining:
            exact+=1;remaining.remove(name);continue
        matches=sorted(((difflib.SequenceMatcher(None,name,x).ratio(),x) for x in remaining),reverse=True)
        if matches and matches[0][0]>.84:
            fuzzy+=1;remaining.remove(matches[0][1]);continue
        missing.append(row)
    return {'matched':exact+fuzzy,'exact':exact,'missed':missing,'extra':len(remaining)}


def main():
    a=argparse.ArgumentParser();a.add_argument('--folder',default='/private');args=a.parse_args()
    folder=Path(args.folder)
    meta=json.loads((folder/'elektr_meta.json').read_text(encoding='utf-8'))
    refs=list(dict.fromkeys(meta['reference']))
    pages=[json.loads((folder/f'elektr{p}_ocr.json').read_text(encoding='utf-8'))['lines'] for p in (1,2)]
    cal=calibrate_electric(pages[0])
    found=[]
    for i,lines in enumerate(pages,1):
        found+=detect((folder/f'elektr{i}.jpg').read_bytes(),lines,cal,has_header=i==1)
    print('PRINTED_LABELS',len(found),'UNIQUE_REFERENCE',len(refs),flush=True)
    for t in (8,15,25,40,60,80,100,140):
        selected=[x for x in found if max(x[1],x[2])>=t]
        r=score(refs,selected)
        print('THRESHOLD',t,'detected',len(selected),'matched',r['matched'],'extra',r['extra'],'missed',r['missed'][:10],flush=True)
    for x in found:
        if 'Wago zamykane' in x[0]:print('WAGO_DIAGNOSTIC',x,flush=True)

if __name__=='__main__':main()
