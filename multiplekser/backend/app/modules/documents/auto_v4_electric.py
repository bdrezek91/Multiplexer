"""AUTO V4 ELECTRIC shadow: OCR token geometry, no document mutations.

Unlike blue handwriting in hydraulics, electrical material quantities may be
printed or dark handwritten. OCR text boxes give a fast, auditable candidate,
not permission to auto-issue without independent GOLD validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any


@dataclass(frozen=True)
class ElectricCalibration:
    issued_x: float
    used_x: float
    header_y: float


@dataclass(frozen=True)
class ElectricCandidate:
    page: int
    name: str
    issued: float | None
    used: float | None
    issued_conf: float | None
    used_conf: float | None
    warnings: tuple[str, ...]


def center(line: dict[str,Any]) -> tuple[float,float]:
    box=line.get('box') or []
    if len(box)<3:raise ValueError('OCR box missing')
    return sum(float(x[0]) for x in box)/len(box),sum(float(x[1]) for x in box)/len(box)


def normalized(value: object) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD',str(value or '').lower())
                   if not unicodedata.combining(ch))


def calibrate_electric(lines: list[dict[str,Any]]) -> ElectricCalibration:
    issued=consumed=None
    for line in lines:
        name=normalized(line.get('text'))
        if 'ilosc' in name and 'wydana' in name:issued=center(line)
        if 'ilosc' in name and 'zuzyta' in name:consumed=center(line)
    if issued is None or consumed is None:
        raise ValueError('Cannot calibrate electric quantity column centers')
    gap=consumed[0]-issued[0]
    if not 80<gap<350 or abs(consumed[1]-issued[1])>45:
        raise ValueError('Electrical grid not recognized')
    return ElectricCalibration(issued[0],consumed[0],(issued[1]+consumed[1])/2)


def _read_number(text: str) -> float | None:
    text=text.strip().replace(',','.')
    if not re.fullmatch(r'(?:\d{1,5})(?:\.\d{1,2})?',text):return None
    val=float(text)
    return val if 0<val<100000 else None


def electric_rows(lines: list[dict[str,Any]],calibration: ElectricCalibration,*,
                  page: int,has_header: bool) -> tuple[list[ElectricCandidate],list[str]]:
    """Use page-one header centers to read continuation pages. All warnings retained."""
    if page<1:raise ValueError('invalid page')
    x_issue=calibration.issued_x;x_used=calibration.used_x
    gap=x_used-x_issue
    min_y=calibration.header_y+28 if has_header else 110
    if not 80<gap<350:raise ValueError('invalid calibration')
    labels=[];numeric=[]
    for i,line in enumerate(lines):
        try:x,y=center(line)
        except (ValueError,TypeError,IndexError):continue
        if y<=min_y:continue
        txt=str(line.get('text') or '').strip()
        if not txt:continue
        if x<x_issue-gap/2-20 and len(txt)>=3 and normalized(txt) not in {'inne:','inne','nazwa','pracownik'}:
            labels.append((y,txt))
        else:
            val=_read_number(txt)
            if val is None:continue
            col='issued' if abs(x-x_issue)<gap*.44 else 'used' if abs(x-x_used)<gap*.44 else None
            if col:
                conf=line.get('score')
                numeric.append((y,col,val,round(float(conf),4) if isinstance(conf,(int,float)) else None,txt))
    labels.sort(key=lambda r:r[0])
    if not labels:raise ValueError('no material label rows found')
    dedup=[]
    for y,name in labels:
        if dedup and abs(dedup[-1][0]-y)<10:continue
        dedup.append((y,name))
    results=[];assigned=set();notices=[]
    for n,(y,name) in enumerate(dedup):
        # Neighbouring rows must not receive one another's quantities.
        up=(y+dedup[n-1][0])/2 if n else y-20
        down=(y+dedup[n+1][0])/2 if n+1<len(dedup) else y+20
        bound=min(18,max(10,(down-up)*.42))
        cells={}
        warnings=[]
        for column in ('issued','used'):
            potentials=[(i,row) for i,row in enumerate(numeric) if i not in assigned
                        and row[1]==column and up<=row[0]<down and abs(row[0]-y)<=bound]
            if len(potentials)>1:
                warnings.append(column+'_multiple_ocr_numbers')
                for i,_ in potentials:assigned.add(i)
                cells[column]=(None,None)
            elif len(potentials)==1:
                i,row=potentials[0];assigned.add(i)
                cells[column]=(row[2],row[3])
                if row[3] is None or row[3]<.85:warnings.append(column+'_low_ocr_confidence')
            else:
                cells[column]=(None,None)
        if cells['issued'][0] is not None or cells['used'][0] is not None or warnings:
            results.append(ElectricCandidate(page=page,name=name,
                           issued=cells['issued'][0],used=cells['used'][0],
                           issued_conf=cells['issued'][1],used_conf=cells['used'][1],
                           warnings=tuple(warnings)))
    for i,row in enumerate(numeric):
        if i not in assigned:
            notices.append(f'unassigned_{row[1]}_number_y{round(row[0])}')
    return results,notices
