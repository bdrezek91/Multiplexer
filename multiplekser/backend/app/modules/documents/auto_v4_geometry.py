"""V4 shadow-only form geometry: locate blue ink, NEVER infer issued amounts.

Use line coordinates from the local OCR (RapidOCR/DirectML) to place blue-ink
components in the correct printed row of a scan. Source page/quantity text is
not rewritten. If the form or colors differ, fail closed and retain V3.
"""
from __future__ import annotations

from dataclasses import dataclass
import statistics
import unicodedata
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class MarkedRow:
    page: int
    name: str
    y: int
    issued_blue_pixels: int
    consumed_blue_pixels: int

    @property
    def marked(self) -> bool:
        return self.issued_blue_pixels >= 20 or self.consumed_blue_pixels >= 20


def _plain(value: object) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(value or "").lower())
                   if not unicodedata.combining(c))


def _center(line: dict) -> tuple[float, float]:
    points=line.get("box") or []
    if len(points) < 3:
        raise ValueError("Missing OCR coordinates")
    return (sum(float(v[0]) for v in points)/len(points),
            sum(float(v[1]) for v in points)/len(points))


def blue_rows(image_jpg: bytes, lines: list[dict[str, Any]], *, page: int) -> list[MarkedRow]:
    """Return all printed lines and blue-ink pixel counts in each quantity cell.

    Do not infer quantities, drop names, or mark the document as complete.
    """
    im=cv2.imdecode(np.frombuffer(image_jpg,dtype=np.uint8),cv2.IMREAD_COLOR)
    if im is None:
        raise ValueError("Invalid JPG")
    header_issued=header_consumed=None
    for line in lines:
        text=_plain(line.get("text"))
        try:
            x,y=_center(line)
        except (TypeError,ValueError,IndexError):
            continue
        # Scans often confuse the capital I in 'Ilość' with small l.
        # Use the distinctive second word plus header position/columns.
        if not (x>im.shape[1]*.5 and 70<y<im.shape[0]*.35):
            continue
        if "wydana" in text:
            header_issued=(x,y)
        if "zuzyta" in text:
            header_consumed=(x,y)
    if not header_issued or not header_consumed:
        raise ValueError("Cannot locate both independent quantity columns")
    x_i,y_head=header_issued
    x_c,y_c=header_consumed
    gap=x_c-x_i
    if gap < 50 or abs(y_head-y_c)>30:
        raise ValueError("Unexpected issue/usage column geometry")
    mid=(x_i+x_c)/2
    issue_l=int(max(0,x_i-gap/2))
    issue_r=int(min(im.shape[1],mid))
    consume_l=issue_r
    consume_r=int(min(im.shape[1],x_c+gap/2))
    if issue_l>=issue_r or consume_l>=consume_r:
        raise ValueError("No quantity cell image region")

    found=[]
    for line in lines:
        try:xc,y=_center(line)
        except (TypeError,ValueError,IndexError):continue
        if not (y_head+20<y<im.shape[0]-10 and 0<xc<issue_l-8):
            continue
        text=str(line.get("text") or "").strip()
        if len(text)<2 or _plain(text) in {"nazwa", "inne:"}:
            continue
        found.append((int(round(y)),text))
    found.sort(key=lambda x:x[0])
    anchors=[]
    for y,name in found:
        if anchors and abs(y-anchors[-1][0])<15:
            continue
        anchors.append((y,name))
    if not anchors:
        raise ValueError("No printed material rows")
    pitches=[b[0]-a[0] for a,b in zip(anchors,anchors[1:]) if 20<=b[0]-a[0]<=65]
    pitch=statistics.median(pitches) if pitches else 36
    margin=min(18,max(13,round(pitch*.48)))
    b=im[:,:,0].astype(np.int16)
    g=im[:,:,1].astype(np.int16)
    r=im[:,:,2].astype(np.int16)
    blue=((b-r)>34)&((b-g)>8)&(r<205)&(b>100)
    # Count ink inside the actual row rectangles instead of using connected-
    # component centroids. A handwritten digit can touch a horizontal rule and
    # merge with an adjacent row; its centroid may then assign the entire mark
    # to the WRONG row or column (observed for 'Mufa GZ').
    counts=[]
    for index,(y,name) in enumerate(anchors):
        top = max(0, round((anchors[index-1][0]+y)/2)) if index else max(0,y-margin)
        bottom = min(im.shape[0],round((y+anchors[index+1][0])/2)) if index+1<len(anchors) else min(im.shape[0],y+margin)
        # Cap distant midpoints around annotations / missing OCR label rows.
        top = max(top,y-margin)
        bottom = min(bottom,y+margin)
        if bottom<=top:
            counts.append((0,0))
            continue
        counts.append((int(blue[top:bottom,issue_l:issue_r].sum()),
                       int(blue[top:bottom,consume_l:consume_r].sum())))
    return [MarkedRow(page=page,name=name,y=y,
                      issued_blue_pixels=counts[i][0],consumed_blue_pixels=counts[i][1])
            for i,(y,name) in enumerate(anchors)]
