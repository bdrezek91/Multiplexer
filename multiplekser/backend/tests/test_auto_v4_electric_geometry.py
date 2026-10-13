"""V4 shadow geometry regression: never move handwritten numbers to adjacent rows."""
import io
import cv2
import numpy as np
import pytest
from app.modules.documents.auto_v4_electric import (
    calibrate_electric,electric_rows,ElectricCalibration,
)
from app.modules.documents.auto_v4_geometry import blue_rows


def token(text,x,y,confidence=.999):
    return {'text':text,'score':confidence,
      'box':[[x-12,y-8],[x+12,y-8],[x+12,y+8],[x-12,y+8]]}


def test_electric_page1_with_header_and_two_rows():
    lines=[token('Ilość Wydana',200,100),token('Ilość zużyta',360,100),
           token('Przewód 3x1,5',95,160),token('Przewód 3x2,5',95,200),
           token('22',200,160),token('5',200,200),token('3',360,200)]
    c=calibrate_electric(lines)
    rows,unused=electric_rows(lines,c,page=1,has_header=True)
    assert not unused and len(rows)==2
    assert [(r.issued,r.used) for r in rows]==[(22,None),(5,3)]


def test_electric_continuation_without_header_uses_page_one_columns():
    lines=[token('Korytko 32x15',90,160),token('Wkręty 4x16',90,200),
           token('150',200,200)]
    rows,unused=electric_rows(lines,ElectricCalibration(200,360,100),page=2,has_header=False)
    assert len(rows)==1 and rows[0].name=='Wkręty 4x16'
    assert rows[0].issued==150 and not unused


def test_electric_weak_or_duplicate_token_is_not_accepted_silently():
    c=ElectricCalibration(200,360,100)
    weak=[token('Wkręty 4x16',95,160),token('150',200,160,.64)]
    a,_=electric_rows(weak,c,page=2,has_header=False)
    assert a[0].issued==150 and 'issued_low_ocr_confidence' in a[0].warnings
    dup=weak+[token('140',201,161,.99)]
    b,_=electric_rows(dup,c,page=2,has_header=False)
    assert b[0].issued is None and 'issued_multiple_ocr_numbers' in b[0].warnings


def test_electric_different_row_quantity_stays_unassigned():
    c=ElectricCalibration(200,360,100)
    rows,unused=electric_rows([token('Przewód 3x4',95,200),token('5',200,280)],c,page=2,has_header=False)
    assert not rows
    assert len(unused)==1


def test_electric_missing_header_does_not_guess_columns():
    with pytest.raises(ValueError,match='calibrate'):
        calibrate_electric([token('Przewód 3x4',95,200)])


def test_blue_ink_is_counted_in_correct_material_row_and_column():
    im=np.full((350,600,3),255,dtype=np.uint8)
    cv2.putText(im,'4',(305,172),cv2.FONT_HERSHEY_SIMPLEX,.7,(225,75,30),3)
    cv2.putText(im,'6',(435,213),cv2.FONT_HERSHEY_SIMPLEX,.7,(225,75,30),3)
    ok,encoded=cv2.imencode('.jpg',im)
    assert ok
    lines=[token('Ilość Wydana',305,100),token('Ilość zużyta',435,100),
           token('Mufa GW',95,165),token('Mufa GZ',95,205)]
    result=blue_rows(encoded.tobytes(),lines,page=1)
    assert len(result)==2
    assert result[0].issued_blue_pixels>=20
    assert result[0].consumed_blue_pixels<20
    assert result[1].consumed_blue_pixels>=20
    assert result[1].issued_blue_pixels<20


def test_dark_electric_ink_rescues_unreadable_digit_as_review_only():
    from app.modules.documents.auto_v4_electric import (
        detect_electric_dark_ink, electric_unrecognized_ink,
    )
    im=np.full((340,520,3),255,dtype=np.uint8)
    # Black handwritten mark unrecognized by text OCR (no numeric token).
    cv2.putText(im,'3',(200,171),cv2.FONT_HERSHEY_SIMPLEX,.7,(15,15,15),2)
    _,blob=cv2.imencode('.jpg',im)
    lines=[token('Ilość Wydana',200,100),token('Ilość zużyta',360,100),
           token('Wago zamykane potrójne',70,160)]
    c=calibrate_electric(lines)
    numeric,unused=electric_rows(lines,c,page=1,has_header=True)
    assert numeric==[] and unused==[]
    marked=detect_electric_dark_ink(blob.tobytes(),lines,c,page=1,has_header=True)
    assert len(marked)==1 and marked[0].name=='Wago zamykane potrójne'
    assert marked[0].issued_dark_pixels>25
    review=electric_unrecognized_ink(marked,numeric)
    assert review==marked
    assert not hasattr(review[0], 'issued')  # ink is NOT a guessed quantity
