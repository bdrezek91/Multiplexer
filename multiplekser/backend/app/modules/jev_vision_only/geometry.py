"""Adaptive grid detector: no fixed pixel coordinates or row ordering."""
from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
from itertools import combinations
import cv2, fitz, numpy as np
from PIL import Image

class LayoutUncertain(ValueError):
    pass

@dataclass(frozen=True)
class Grid:
    columns: tuple[int,int,int,int,int]
    lines: tuple[int,...]
    width: int
    height: int

@dataclass(frozen=True)
class Row:
    page: int
    index: int
    issued_ink: int
    used_ink: int
    name_png: bytes
    issued_png: bytes
    used_png: bytes
    context_png: bytes

def _merge(values, tolerance):
    groups=[]
    for v in sorted(values):
        if not groups or v-groups[-1][-1]>tolerance: groups.append([v])
        else: groups[-1].append(v)
    return [int(np.median(g)) for g in groups]

def _broken_grid_columns(gray: np.ndarray) -> list[int]:
    """Conservative second attempt on faxed scans with interrupted vertical rules.

    Does not infer columns from the original form. If plausible alternatives
    are too close in score, asks for review rather than guessing.
    """
    h,w=gray.shape
    mask=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,21,5)
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT,(1,7)))
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(60,round(h*.09)))))
    n,_,stats,_=cv2.connectedComponentsWithStats(mask)
    positions=[]
    for x,y,width,height,area in stats[1:]:
        if height>h*.11 and width<=max(18,w//70) and w*.03<x<w*.98:
            positions.append((int(x+width//2),int(height)))
    clusters=[]
    for x,length in sorted(positions):
        if not clusters or x-clusters[-1][-1][0]>14:clusters.append([(x,length)])
        else:clusters[-1].append((x,length))
    merged=[(int(np.median([v[0] for v in group])),max(v[1] for v in group))
            for group in clusters]
    candidates=sorted(merged,key=lambda p:p[1],reverse=True)[:13]
    valid=[]
    for trial in combinations(sorted(candidates),5):
        coords=[item[0] for item in trial]
        if coords[0]>w*.2 or coords[-1]<w*.70:continue
        if coords[1]-coords[0]<w*.25:continue
        if any(b-a<w*.06 for a,b in zip(coords[1:],coords[2:])):continue
        score=sum(item[1] for item in trial)
        valid.append((score,coords))
    if not valid:return []
    valid.sort(key=lambda item:item[0],reverse=True)
    # Reject virtually equal solutions which imply ambiguous printed columns.
    if len(valid)>1 and valid[1][0]>valid[0][0]*.988:
        return []
    return valid[0][1]


def grid_from_rgb(rgb: np.ndarray) -> Grid:
    if rgb.ndim!=3 or rgb.shape[2]!=3: raise LayoutUncertain("RGB required")
    h,w=rgb.shape[:2]
    if h<400 or w<350: raise LayoutUncertain("page too small")
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    binary=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(1,max(80,h//5))))
    n,_,stats,_=cv2.connectedComponentsWithStats(vertical)
    xs=_merge([int(x+width//2) for x,y,width,height,area in stats[1:]
        if height>=h*.22 and width<=max(15,w//80)],12)
    if len(xs)!=5:
        xs=_broken_grid_columns(gray)
    if len(xs)!=5: raise LayoutUncertain("unknown or ambiguous table columns")
    if xs[1]-xs[0]<w*.25 or any(b-a<w*.04 for a,b in zip(xs,xs[1:])):
        raise LayoutUncertain("ambiguous columns")
    horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(max(60,w//4),1)))
    n,_,stats,_=cv2.connectedComponentsWithStats(horizontal)
    ys=_merge([int(y+height//2) for x,y,width,height,area in stats[1:]
        if width>.65*(xs[-1]-xs[0]) and x<=xs[0]+15
        and x+width>=xs[-1]-15 and height<=max(12,h//100)],4)
    if len(ys)<8:
        # Faxed greyscale sheets may erase thin rules from Otsu. Use adaptive
        # binarization only when the first method has failed, and insist on
        # complete full-width lines aligned with the observed column bounds.
        alternate=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,21,5)
        alternate=cv2.morphologyEx(alternate,cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT,(max(50,w//14),1)))
        n,_,st,_=cv2.connectedComponentsWithStats(alternate)
        ys=_merge([int(y+height//2) for x,y,width,height,area in st[1:]
            if width>.65*(xs[-1]-xs[0]) and x<=xs[0]+15
            and x+width>=xs[-1]-18 and height<=max(12,h//100)],4)
    if len(ys)<8: raise LayoutUncertain(f"too few table row borders: {len(ys)}")
    typical=float(np.median([b-a for a,b in zip(ys,ys[1:]) if 10<=b-a<=100] or [0]))
    if not 12<=typical<=100: raise LayoutUncertain("unreliable row spacing")
    return Grid(tuple(xs),tuple(ys),w,h)

def _png(arr: np.ndarray) -> bytes:
    im=Image.fromarray(arr,'RGB')
    w,h=im.size
    canvas=Image.new('RGB',(max(320,w),max(320,h)),'white')
    canvas.paste(im,(max(0,(320-w)//2),max(0,(320-h)//2)))
    buf=BytesIO();canvas.save(buf,format='PNG');return buf.getvalue()

def _ink(arr):
    """Count plausible handwriting, not black table borders.

    Otsu background noise and clipped horizontal grid strokes can otherwise
    mark EVERY row as handwritten. Keep thin upright digits (1) and checkmarks.
    This is only a candidate detector, never a trusted blank-cell decision.
    """
    if not arr.size:return 0
    gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    dark=(gray<180).astype(np.uint8)*255
    w=gray.shape[1]
    # Remove near-horizontal printed row separators, preserving digit stems.
    long_horizontal=cv2.morphologyEx(dark,cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,(max(12,w//8),1)))
    candidates=cv2.subtract(dark,long_horizontal)
    n,_,stats,_=cv2.connectedComponentsWithStats(candidates)
    total=0
    for x,y,ww,hh,area in stats[1:]:
        if area<7 or hh<3:continue
        # Slanted/clipped row boundary: wider than a digit and almost flat.
        if ww>=max(18,w//5) and hh<=5:continue
        total+=int(area)
    return total

def extract_rows(rgb:np.ndarray,grid:Grid,page:int)->list[Row]:
    xs=grid.columns;out=[]
    for index,(a,b) in enumerate(zip(grid.lines,grid.lines[1:]),1):
        if not 15<=b-a<=110:continue
        top,bottom=a+3,b-3
        if bottom<=top+6:continue
        def slice_at(x0,x1):return rgb[top:bottom,x0+5:x1-5].copy()
        name,issued,used=slice_at(xs[0],xs[1]),slice_at(xs[1],xs[2]),slice_at(xs[2],xs[3])
        context=rgb[max(0,a-6):min(rgb.shape[0],b+6),xs[0]:xs[4]].copy()
        out.append(Row(page,index,_ink(issued),_ink(used),_png(name),_png(issued),_png(used),_png(context)))
    return out

def render_pdf_pages(data:bytes,max_pages:int=4)->list[np.ndarray]:
    if not data.startswith(b'%PDF'):raise LayoutUncertain("not a PDF")
    with fitz.open(stream=data,filetype='pdf') as doc:
        if not 1<=len(doc)<=max_pages:raise LayoutUncertain(f"unacceptable page count: {len(doc)}")
        pages=[]
        for page in doc:
            pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            if pix.n!=3:raise LayoutUncertain("unexpected image channels")
            pages.append(np.frombuffer(pix.samples,np.uint8).reshape(pix.height,pix.width,3).copy())
        return pages

def _hough_deskew_angle(rgb: np.ndarray) -> float | None:
    """Conservative skew estimate from consistently horizontal printed rules.

    Only returned when several agreeing Hough segments exist. Never deskew
    from printed text distribution or arbitrary minAreaRect.
    """
    from app.modules.ocr.image import _hough_line_angle_deg

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    angle = _hough_line_angle_deg(gray)
    if angle is None or not 0.8 <= abs(angle) <= 12:
        return None
    return float(angle)


def _deskew_rgb(rgb: np.ndarray, angle: float) -> np.ndarray:
    h, w = rgb.shape[:2]
    mat = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(rgb, mat, (w, h), flags=cv2.INTER_CUBIC,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def detect_page(rgb:np.ndarray,page:int)->tuple[Grid,list[Row]]:
    # Try untouched scan first. Only transform when confident straight rules
    # say the grid is rotated and the original segmentation failed.
    try:
        grid = grid_from_rgb(rgb)
        return grid, extract_rows(rgb, grid, page)
    except LayoutUncertain as original:
        angle = _hough_deskew_angle(rgb)
        if angle is None:
            raise original
        rotated = _deskew_rgb(rgb, angle)
        try:
            grid = grid_from_rgb(rotated)
            return grid, extract_rows(rotated, grid, page)
        except LayoutUncertain as exc:
            raise LayoutUncertain(
                f"{original}; deskew {angle:+.2f} deg inconclusive: {exc}"
            ) from exc
