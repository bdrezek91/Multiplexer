#!/usr/bin/env python3
"""V4 read-only geometry detector: crop handwritten quantity cells, never book.

Discovers grid lines from pixels (no fixed row numbers). Prints an auditable
report and saves only sample cell crops with blue handwriting for inspection.
Does NOT assign material codes/names: multiple form variants exist.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from PIL import Image
import numpy as np


def _group(indices: np.ndarray, max_gap: int=3) -> list[list[int]]:
    groups=[]
    for y in indices:
        y=int(y)
        if not groups or y-groups[-1][-1]>max_gap:
            groups.append([])
        groups[-1].append(y)
    return groups


def identify_columns(image: np.ndarray) -> tuple[int,int,int] | None:
    h,w=image.shape[:2]
    gray=(image[:,:,0].astype(np.int16)+image[:,:,1]+image[:,:,2])//3
    upper=int(h*.27)
    lower=int(h*.68)
    projection=(gray[upper:lower:4,:] < 160).mean(axis=0)
    # Proportional bands are only hints; actual borders MUST be measured.
    proportions=(.56,.71,.84)
    picked=[]
    for prop in proportions:
        a,b=int(w*(prop-.035)),int(w*(prop+.035))
        strongest=int(a+np.argmax(projection[a:b]))
        if projection[strongest] < .39:
            return None
        picked.append(strongest)
    if not (picked[0]+70<picked[1] and picked[1]+70<picked[2]):
        return None
    return tuple(picked)


def find_table_rows(image: np.ndarray, columns: tuple[int,int,int]) -> list[tuple[int,int]]:
    h,w=image.shape[:2]
    gray=(image[:,:,0].astype(np.int16)+image[:,:,1]+image[:,:,2])//3
    # Paper/table lines span from labels up through both quantity cells.
    left=int(w*.15)
    right=min(w-1,columns[2]+25)
    strength=(gray[:,left:right:2]<170).mean(axis=1)
    lines=_group(np.flatnonzero((strength>.39) &
        (np.arange(h)>int(h*.05)) & (np.arange(h)<int(h*.96))))
    positions=[int(np.median(group)) for group in lines]
    # Page 1 includes four long metadata rows plus the column header.
    # Other pages begin with just the printed column-header row.
    if len(positions)>=7 and all(42 <= positions[i+1]-positions[i] <= 50 for i in range(4)):
        positions=positions[5:]
    # Never invent a missing horizontal line. Missing rows remain unassigned.
    return [(a,b) for a,b in zip(positions,positions[1:]) if 24<=b-a<=48]


def _blue_count(rgb: np.ndarray) -> int:
    pix=rgb.astype(np.int16)
    return int(np.count_nonzero(
        (pix[:,:,2] > pix[:,:,0]+23) &
        (pix[:,:,2] > pix[:,:,1]+9) &
        (pix[:,:,0] < 185) &
        (pix[:,:,1] < 195)
    ))


def analyze(image_path:Path,output:Path,*,max_samples:int=7)->dict:
    with Image.open(image_path) as pil:
        image=np.array(pil.convert('RGB'))
    geometry=identify_columns(image)
    report={"filename":image_path.name,"shape":list(image.shape[:2]),
            "columns_x":list(geometry) if geometry else None,"usable_rows":0,
            "blue_rows":0,"samples":[],"mode":"shadow_only"}
    if not geometry:
        report["reason"]="No reliable vertical grid boundaries"
        return report
    rows=find_table_rows(image,geometry)
    report["usable_rows"]=len(rows)
    if len(rows)<8:
        report["reason"]="Too few horizontal grid lines — unknown form, fail closed"
        return report
    for i,(y0,y1) in enumerate(rows):
        x0,x1,x2=geometry
        issued=image[y0+3:y1-2,x0+4:x1-3]
        used=image[y0+3:y1-2,x1+4:x2-3]
        blue=_blue_count(issued)+_blue_count(used)
        if blue<5:
            continue
        report["blue_rows"]+=1
        if len(report["samples"])>=max_samples:
            continue
        # Both independent handwritten quantity cells; labels intentionally
        # not assigned until printed row anchoring/template variant is verified.
        piece=Image.fromarray(np.concatenate((issued,used),axis=1))
        piece=piece.resize((piece.width*3,piece.height*3),Image.Resampling.LANCZOS)
        name=f"{image_path.stem}_row_{i+1:02d}.png"
        piece.save(output/name)
        report["samples"].append({"row_slot":i+1,"pixel_rows":[y0,y1],
                                  "blue_pixels":blue,"crop":name})
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pages",nargs="+",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    reports=[analyze(p,args.output) for p in args.pages]
    report={"version":"V4 geometry shadow 0.1","pages":reports,
            "warning":"Do NOT map row slot to product until all template variants are verified."}
    destination=args.output/"report.json"
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    destination.chmod(0o600)
    print(json.dumps({"page_count":len(reports),
       "rows_detected":sum(p["usable_rows"] for p in reports),
       "rows_with_blue":sum(p["blue_rows"] for p in reports),
       "by_page":[{"name":p["filename"],"rows":p["usable_rows"],
        "blue":p["blue_rows"],"cols":p["columns_x"]} for p in reports]},ensure_ascii=False))


if __name__=="__main__":main()
