"""Read-only electric OCR geometry vs stored results (NOT independent GOLD)."""
import argparse
import difflib
import json
from pathlib import Path
from sqlalchemy import text
from app.core.db import engine
from app.modules.products.catalog import plain_norm
from app.modules.documents.auto_v4_electric import calibrate_electric,electric_rows


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--folder',default='/private')
    p.add_argument('--document',required=True,help='Completed electricity OCR document ID')
    args=p.parse_args();folder=Path(args.folder)
    with engine.connect() as con:
        source=con.execute(text('SELECT dzial,status FROM document WHERE id=:id'),{'id':args.document}).mappings().one()
        if source['dzial']!='elektryka' or source['status']!='done':raise ValueError('not completed electric')
        refs=[dict(r) for r in con.execute(text('SELECT rozpoznana_nazwa,ilosc_wydana,ilosc_zuzyta FROM document_item WHERE document_id=:id ORDER BY sequence'),{'id':args.document}).mappings()]
    filelist=[json.loads((folder/f'elektr{p}_ocr.json').read_text(encoding='utf-8'))['lines'] for p in (1,2)]
    calibration=calibrate_electric(filelist[0])
    print('CALIBRATION',calibration,flush=True)
    candidates=[];warnings=[]
    for index,lines in enumerate(filelist):
        rows,unused=electric_rows(lines,calibration,page=index+1,has_header=index==0)
        print('PAGE',index+1,'extracted',len(rows),'unassigned',len(unused),'sample',unused[:7],flush=True)
        candidates.extend(rows);warnings.extend(unused)
    remaining=candidates.copy();exact=qty_correct=0;fuzzy=0;diff=[];missed=[];low_conf=[]
    for ref in refs:
        name=plain_norm(ref['rozpoznana_nazwa'])
        selected=next((c for c in remaining if plain_norm(c.name)==name),None)
        if selected is None:
            matches=sorted(((difflib.SequenceMatcher(None,name,plain_norm(c.name)).ratio(),c) for c in remaining),key=lambda t:t[0],reverse=True)
            if matches and matches[0][0]>=.84:
                selected=matches[0][1];fuzzy+=1
        else:exact+=1
        if selected is None:missed.append(ref['rozpoznana_nazwa']);continue
        remaining.remove(selected)
        numeric=(float(ref['ilosc_wydana']) if ref['ilosc_wydana'] is not None else None,
                 float(ref['ilosc_zuzyta']) if ref['ilosc_zuzyta'] is not None else None)
        proposed=(selected.issued,selected.used)
        if numeric==proposed:qty_correct+=1
        else:diff.append({'name':ref['rozpoznana_nazwa'],'db':numeric,'geometry':proposed})
        if selected.warnings:low_conf.append({'name':selected.name,'warnings':selected.warnings})
    print('ELECTRIC_BENCH',json.dumps({'reference':len(refs),'candidates':len(candidates),'exact_names':exact,
          'fuzzy_names':fuzzy,'matched':exact+fuzzy,'quantity_pairs_exact':qty_correct,
          'qty_differences':diff[:15],'missed_names':missed[:15],
          'extra_names':[c.name for c in remaining][:12],'review':low_conf[:12],
          'unassigned_numeric':warnings[:18]},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
