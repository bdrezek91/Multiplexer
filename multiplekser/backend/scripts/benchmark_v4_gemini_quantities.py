"""Strict read-only Gemini OCR of cropped handwritten quantity cells, never writes items."""
import argparse
import asyncio
import base64
import json
import time
import unicodedata
import re
from pathlib import Path
import httpx
from app.core.config import settings

SCHEMA={"type":"object","properties":{"rows":{"type":"array","items":{
        "type":"object","properties":{"id":{"type":"integer"},
        "wyd":{"type":["number","null"]},"zuz":{"type":["number","null"]}},
        "required":["id","wyd","zuz"]}}},"required":["rows"]}

PROMPT='''To są WYCIĘTE NIEBIESKIE ZAPISY ilości na wydawce magazynowej.
Każdy wiersz ma numer po lewej (01,02...), a dalej dwie kolumny WYDANA i ZUŻYTA.
Ptaszek V lub ✓ to NIE liczba. Odręczna / może oznaczać 1, pozioma kreska - brak.
Nie przenoś danych między wierszami ani kolumnami. Odczytaj odręczne cyfry dosłownie,
nie zgaduj. Puste lub nieczytelne pole to null.
Oddaj wszystkie identyfikatory dokładnie raz w JSON rows, w oryginalnej kolejności.
Bez nazw materiałów i komentarzy. Liczby jako liczby JSON albo null.
'''

def norm(s):
    s=unicodedata.normalize('NFKD',str(s or '').lower())
    return re.sub('[^a-z0-9]','', ''.join(c for c in s if not unicodedata.combining(c)))

def qty(x):
    if x is None:return None
    try:return float(str(x).replace(',','.'))
    except (ValueError,TypeError):return None

async def main():
    cli=argparse.ArgumentParser()
    cli.add_argument('--folder',default='/private')
    cli.add_argument('--page',type=int,default=1)
    cli.add_argument('--model',default='gemini-3.6-flash')
    cli.add_argument('--timeout',type=float,default=14)
    args=cli.parse_args()
    if args.model not in {'gemini-3.6-flash','gemini-3.5-flash-lite','gemini-3.1-flash-lite'}:raise ValueError('model')
    data=json.loads((Path(args.folder)/'quantity_mapping.json').read_text(encoding='utf-8'))
    marked=data['pages'][str(args.page)]
    reference={norm(x['rozpoznana_nazwa']):x for x in data['reference']}
    sheet=(Path(args.folder)/f'quantity_sheet{args.page}.jpg').read_bytes()
    prompt=PROMPT+f'Liczba wierszy: {len(marked)}, numery 01 do {len(marked):02d}.'
    request={'contents':[{'parts':[{'inlineData':{'mimeType':'image/jpeg','data':base64.b64encode(sheet).decode('ascii')}},{'text':prompt}]}],
      'generationConfig':{'temperature':0,'thinkingConfig':{'thinkingLevel':'minimal'},
      'responseMimeType':'application/json','responseJsonSchema':SCHEMA}}
    started=time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(args.timeout)) as client:
            resp=await client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{args.model}:generateContent',
                 json=request,headers={'x-goog-api-key':settings.gemini_api_key_free})
        elapsed=round(time.perf_counter()-started,3)
        if not resp.is_success:
            print('GEMINI_QTY_API_ERROR',args.model,'HTTP',resp.status_code,'seconds',elapsed,
                  'status',resp.json().get('error',{}).get('status'),flush=True);return
        payload=resp.json()
        content=''.join(p.get('text','') for c in payload.get('candidates',[]) for p in (c.get('content') or {}).get('parts',[]))
        obj=json.loads(content)
        rows=obj.get('rows',[]) if isinstance(obj,dict) else []
        mapping={int(x['id']):x for x in rows if isinstance(x,dict) and isinstance(x.get('id'),int)}
        compared=correct=0;diff=[]
        for item in marked:
            ref=reference.get(norm(item['name']))
            if ref is None:continue
            compared+=1
            actual=(qty(ref['ilosc_wydana']),qty(ref['ilosc_zuzyta']))
            predicted=mapping.get(item['id'],{})
            proposed=(qty(predicted.get('wyd')),qty(predicted.get('zuz')))
            if actual==proposed:correct+=1
            else:diff.append({'name':item['name'],'baseline':actual,'test':proposed})
        report={'model':args.model,'page':args.page,'seconds':elapsed,
             'rows_expected':len(marked),'rows_reported':len(rows),'rows_compared_non_gold':compared,
             'exact_pairs':correct,'mismatches':diff[:10],
             'prompt_tokens':payload.get('usageMetadata',{}).get('promptTokenCount'),
             'output_tokens':payload.get('usageMetadata',{}).get('candidatesTokenCount')}
        print('GEMINI_QTY_RESULT',json.dumps(report,ensure_ascii=False),flush=True)
        dest=Path(args.folder)/f'gemini_quantity_page{args.page}.json'
        dest.write_text(json.dumps({'report':report,'rows':rows},ensure_ascii=False),encoding='utf-8');dest.chmod(0o600)
    except Exception as e:
        print('GEMINI_QTY_EXCEPTION',args.model,type(e).__name__,round(time.perf_counter()-started,3),flush=True)

if __name__=='__main__':asyncio.run(main())
