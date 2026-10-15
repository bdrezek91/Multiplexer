"""JEV Image-only experimental OCR. No Gemini, no Claude, no DB writes.

Printed labels are selected from known candidates (NOT generative OCR). New labels,
unknown geometry and ambiguous quantities MUST remain review-required.
"""
from __future__ import annotations
from io import BytesIO
import cv2
import numpy as np
from PIL import Image
from collections import defaultdict
import httpx

from .geometry import render_pdf_pages, detect_page, LayoutUncertain, Row
from .client import ImageQuestion, ask_images, JevVisionError
from app.modules.ocr.form_rows_elektryka import FORM_ROWS as ELECTRIC
from app.modules.ocr.form_rows_hydraulika import FORM_ROWS as HYDRAULIC, ADDITIONAL_ROWS as HYDRAULIC_EXTRA
from app.modules.products.catalog import plain_norm

NUMBERS=tuple(map(str,range(0,51)))+("60","70","75","80","90","100","120","150","200","250","300","400","500","1000")
QUANTITIES={("qty_"+n):"Handwritten quantity exactly "+n+" (not the printed table line, not a V/checkmark)." for n in NUMBERS}
QUANTITIES.update({
 "blank":"There is no handwritten number in this quantity cell.",
 "check_only":"There is only a checkmark / V, not a number.",
 "dash":"A dash or cross-out without valid numeric quantity.",
 "unreadable":"Different or unclear number; cannot reliably read it."
})

def groups_for_department(department:str)->dict[str,list[str]]:
    if department=="elektryka":names=list(ELECTRIC)
    elif department=="hydraulika":names=list(HYDRAULIC)+list(HYDRAULIC_EXTRA)
    else:raise ValueError("unknown department")
    result=defaultdict(list)
    for name in names:
        words=plain_norm(name).split()
        if words and name not in result[words[0]]:
            result[words[0]].append(name)
    return dict(result)

def select_marked(rows:list[Row],limit:int=12)->tuple[list[Row],int]:
    # Deterministic candidate only. All nonselected rows remain coverage gap,
    # never reported to be conclusively blank.
    flagged=[r for r in rows if r.issued_ink>=8 or r.used_ink>=8]
    return flagged[:limit],max(0,len(flagged)-limit)

def enhanced_quantity_png(raw_png: bytes) -> bytes:
    """Independent high-contrast view preserving all handwritten strokes.

    This DOES NOT strip a colour channel (which could erase black writing),
    or produce a truth label. Both original and enhanced JEV choices must agree.
    """
    raw=np.array(Image.open(BytesIO(raw_png)).convert('RGB'))
    light=cv2.cvtColor(raw,cv2.COLOR_RGB2LAB)
    light[:,:,0]=cv2.createCLAHE(clipLimit=1.8,tileGridSize=(6,6)).apply(light[:,:,0])
    out=cv2.cvtColor(light,cv2.COLOR_LAB2RGB)
    stream=BytesIO();Image.fromarray(out).save(stream,format='PNG')
    return stream.getvalue()


def _grid_gap_diagnostics(grid) -> dict:
    gaps=[b-a for a,b in zip(grid.lines,grid.lines[1:])]
    typical=float(np.median([g for g in gaps if 15<=g<=110] or [0]))
    unresolved=[]
    if typical:
        # Segment skipping must be explicit: a 2x row-height gap might
        # contain one or more rows not found by the morphology detector.
        unresolved=[{'after_line':i,'height':gap} for i,gap in enumerate(gaps)
                    if gap>max(110,typical*1.8)]
    return {'median_row_gap':round(typical,1),'large_unresolved_intervals':unresolved}


def _batches(questions,size=12):
    for i in range(0,len(questions),size):
        yield questions[i:i+size]

def analyze_pdf(pdf_bytes:bytes,department:str,*,max_pages:int=4,
                max_marked:int=12,page_limit:int|None=None,
                verify_quantities:bool=False,api_client:httpx.Client|None=None)->dict:
    groups=groups_for_department(department)
    if not groups:raise ValueError("no material candidates")
    full_pages=render_pdf_pages(pdf_bytes,max_pages=max_pages)
    if page_limit is not None and not 1<=page_limit<=len(full_pages):
        raise ValueError("page limit outside document")
    pages=full_pages[:page_limit] if page_limit is not None else full_pages
    diagnostics=[]
    rows=[]
    layout_failures=[]
    for i,p in enumerate(pages,1):
        try:
            grid,page_rows=detect_page(p,i)
            rows.extend(page_rows)
            diagnostics.append({"page":i,"columns":list(grid.columns),
                               "grid_rows":len(page_rows),"line_count":len(grid.lines),
                               **_grid_gap_diagnostics(grid)})
        except LayoutUncertain as exc:
            layout_failures.append({"page":i,"reason":str(exc)})
    # Never call this a full-document OCR if even one page could not be segmented.
    if layout_failures:
        return {"status":"layout_uncertain","department":department,
                "diagnostics":diagnostics,"layout_failures":layout_failures,
                "rows":[],"coverage_complete":False,"provider":"JEV Image ONLY"}
    marked,skipped=select_marked(rows,max_marked)
    if not marked:
        return {"status":"no_ink_detected_review","department":department,
                "diagnostics":diagnostics,"rows":[],"coverage_complete":False,
                "provider":"JEV Image ONLY"}
    family_choices={g:"Printed material name begins with "+g.replace("_"," ")+"."
                    for g in groups}
    family_choices["unknown"]="Different, new, illegible or unknown printed material."
    if len(family_choices)>250:
        return {"status":"too_many_families_review","department":department,
                "diagnostics":diagnostics,"rows":[],"coverage_complete":False,
                "provider":"JEV Image ONLY"}

    primary=[]
    for k,r in enumerate(marked):
        primary.append(ImageQuestion(f"r{k}_family",r.name_png,
              "Choose the FIRST printed material-name word/family. Read the actual lettering, not the row position. If it is not listed, choose unknown.",
              family_choices))
        for column,image,ink in (("issued",r.issued_png,r.issued_ink),
                                 ("used",r.used_png,r.used_ink)):
            if ink>=8:
                primary.append(ImageQuestion(f"r{k}_{column}",image,
                    "Read the complete handwritten numerical QUANTITY inside the cell. Ignore black table lines, unit labels, V/checkmarks and marks from adjacent cells. If outside options or unclear, choose unreadable.",
                    QUANTITIES))
    results={}
    try:
        for block in _batches(primary):
            results.update(ask_images(block,client=api_client))
    except JevVisionError as exc:
        return {"status":"jev_api_unavailable","reason":str(exc),"department":department,
                "diagnostics":diagnostics,"rows":[],"coverage_complete":False,
                "provider":"JEV Image ONLY"}

    # Independent second visual reading is OPTIONAL and never authoritative.
    # Inconsistency is explicit: it cannot silently replace the first quantity.
    verified={}
    if verify_quantities:
        review=[]
        for k,r in enumerate(marked):
            for column,image,ink in (("issued",r.issued_png,r.issued_ink),
                                     ("used",r.used_png,r.used_ink)):
                if ink<8:continue
                review.append(ImageQuestion(f"r{k}_{column}_second",
                    enhanced_quantity_png(image),
                    "Independently identify the exact handwritten number on the enhanced cell. "
                    "Do not infer from context. Ignore printed grid and V/checkmark. "
                    "If ambiguous, select unreadable.",QUANTITIES))
        try:
            for block in _batches(review):
                verified.update(ask_images(block,client=api_client))
        except JevVisionError as exc:
            return {"status":"jev_verification_unavailable","reason":str(exc),
                    "department":department,"diagnostics":diagnostics,
                    "rows":[],"coverage_complete":False,"provider":"JEV Image ONLY"}

    # Second pass: choose exact printed name only from the selected family.
    refined=[]
    for k,r in enumerate(marked):
        label=results[f"r{k}_family"].choice
        if label and label in groups:
            criteria={f"option_{i}":value for i,value in enumerate(groups[label])}
            criteria["unknown"]="Printed row does not match any candidate or is unreadable."
            refined.append(ImageQuestion(f"r{k}_name",r.name_png,
                "Select the EXACT printed material description, including diameters, dimensions and national standard. Do not alter numbers or infer from nearby rows.",
                criteria))
    fine={}
    try:
        for block in _batches(refined):
            fine.update(ask_images(block,client=api_client))
    except JevVisionError as exc:
        # Keep amounts, but labels cannot be trusted. Never fill guesses.
        return {"status":"jev_name_stage_unavailable","reason":str(exc),"department":department,
                "diagnostics":diagnostics,"rows":[],"coverage_complete":False,
                "provider":"JEV Image ONLY"}

    out=[]
    for k,r in enumerate(marked):
        family_ans=results[f"r{k}_family"]
        family=family_ans.choice
        name_ans=fine.get(f"r{k}_name")
        name=None
        if family in groups and name_ans is not None and name_ans.choice!="unknown":
            try: name=groups[family][int(name_ans.choice.removeprefix("option_"))]
            except (ValueError,IndexError,AttributeError):pass
        qty={}
        for col,ink in (("issued",r.issued_ink),("used",r.used_ink)):
            a=results.get(f"r{k}_{col}")
            # No '0' or 'V' inferred from absence of ink; mark uncertainty.
            repeat=verified.get(f"r{k}_{col}_second") if verify_quantities else None
            agree=(repeat is not None and a is not None and
                   repeat.choice==a.choice and a.choice is not None)
            raw_choice=a.choice if a else None
            # If verification is active, disagreeing numbers become UNKNOWN.
            # High model confidence does not override the disagreement.
            read=(raw_choice[4:] if raw_choice and raw_choice.startswith("qty_")
                  and (not verify_quantities or agree) else None)
            qty[col]={"read":read,
                      "raw_choice":raw_choice,"confidence":a.confidence if a else None,
                      "second_choice":repeat.choice if repeat else None,
                      "verified_agreement":agree if verify_quantities and a is not None else None,
                      "ink_pixels":ink,"checked_by_jev":a is not None}
        out.append({"page":r.page,"row":r.index,
                    "material_candidate":name,"family":family,
                    "name_confidence":name_ans.confidence if name_ans else None,
                    "issued":qty["issued"],"used":qty["used"],
                    "needs_review":True})
    return {"status":"shadow_experimental","department":department,
            "provider":"JEV Image ONLY","pages":len(pages),
            "diagnostics":diagnostics,"rows":out,
            "candidates_total":len(marked)+skipped,
            "candidate_rows_skipped":skipped,
            "grid_rows_found":len(rows),
            "quantity_crosscheck_enabled":verify_quantities,
            "unresolved_table_intervals":sum(
                len(d.get("large_unresolved_intervals",[])) for d in diagnostics),
            "coverage_complete":False, # cannot claim ALL rows accounted for without independent gold
            "matcher_used":False,"items_approved":0}
