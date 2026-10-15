"""Safety/geometry tests: JEV-only never mutates production and fails closed."""
from __future__ import annotations
from unittest.mock import patch
import numpy as np,cv2,pytest
from app.modules.jev_vision_only.geometry import grid_from_rgb,extract_rows,LayoutUncertain
from app.modules.jev_vision_only.client import ImageAnswer,ImageQuestion,ask_images,JevVisionError
from app.modules.jev_vision_only.engine import analyze_pdf,groups_for_department

def synthetic():
    canvas=np.full((1100,900,3),255,np.uint8)
    xs=(50,450,560,680,800)
    for x in xs:
        cv2.line(canvas,(x,130),(x,850),(0,0,0),2)
    for y in range(130,851,60):
        cv2.line(canvas,(50,y),(800,y),(0,0,0),2)
    cv2.putText(canvas,"Wago",(90,160),cv2.FONT_HERSHEY_SIMPLEX,.75,(0,0,0),2)
    cv2.putText(canvas,"1",(478,167),cv2.FONT_HERSHEY_SIMPLEX,.9,(30,30,30),2)
    return canvas

def test_ink_detector_keeps_thin_digits_and_rejects_table_rule():
    from app.modules.jev_vision_only.geometry import _ink
    blank=np.full((48,140,3),255,np.uint8)
    rule=blank.copy()
    cv2.line(rule,(4,45),(135,45),(0,0,0),2)
    assert _ink(blank)==0
    assert _ink(rule)==0
    one=blank.copy()
    cv2.line(one,(35,13),(34,33),(40,60,130),2)
    assert _ink(one)>=8
    check=blank.copy()
    cv2.line(check,(23,21),(31,30),(40,60,130),2)
    cv2.line(check,(31,30),(43,10),(40,60,130),2)
    assert _ink(check)>=8


def test_dynamic_grid_with_shifted_coordinates():
    a=synthetic()
    grid=grid_from_rgb(a)
    assert len(grid.columns)==5
    assert all(abs(x-y)<15 for x,y in zip(grid.columns,(50,450,560,680,800)))
    rows=extract_rows(a,grid,1)
    assert len(rows)>=10
    assert rows[0].issued_ink>8 and rows[0].used_ink<8
    assert len(rows[0].issued_png)>500

@pytest.mark.parametrize("degrees",[-6.0,6.0])
def test_rotated_form_recovers_grid_without_preset_coordinates(degrees):
    from app.modules.jev_vision_only.geometry import detect_page
    image=synthetic()
    height,width=image.shape[:2]
    rotation=cv2.getRotationMatrix2D((width/2,height/2),degrees,1.0)
    shifted=cv2.warpAffine(image,rotation,(width,height),borderValue=(255,255,255))
    grid,rows=detect_page(shifted,1)
    assert len(grid.columns)==5
    assert len(rows)>=10
    assert rows[0].issued_ink>8


@pytest.mark.parametrize("image",[np.full((1100,900,3),255,np.uint8),np.full((50,30,3),255,np.uint8)])
def test_unknown_or_new_layout_never_creates_fake_rows(image):
    with pytest.raises(LayoutUncertain):grid_from_rgb(image)

def test_quantity_choices_include_multidigit_and_uncertainty():
    from app.modules.jev_vision_only.engine import QUANTITIES
    assert all(("qty_"+x) in QUANTITIES for x in ("1","4","14","40","100","400"))
    assert all(x in QUANTITIES for x in ("unreadable","blank","check_only"))

def test_text_catalog_families_are_data_derived_and_no_fixed_row_index():
    assert any(x.startswith("wago") for x in groups_for_department("elektryka"))
    assert any(x.startswith("kolanko") for x in groups_for_department("hydraulika"))
    with pytest.raises(ValueError):groups_for_department("unknown")

def test_jev_only_shadow_does_not_approve_outputs():
    image=synthetic()
    def fake_call(q,**_):
        reply={}
        for item in q:
            if item.key.endswith("_family"):
                selected="wago"
            elif item.key.endswith("_name"):
                selected="option_0"
            else:selected="qty_1"
            reply[item.key]=ImageAnswer(selected,.93,120,100)
        return reply
    with patch("app.modules.jev_vision_only.engine.render_pdf_pages",return_value=[image]), \
         patch("app.modules.jev_vision_only.engine.ask_images",side_effect=fake_call):
        result=analyze_pdf(b"%PDF-example","elektryka",max_marked=2)
    assert result["status"]=="shadow_experimental"
    assert result["coverage_complete"] is False
    assert result["items_approved"]==0
    assert all(r["needs_review"] for r in result["rows"])
    assert result["provider"]=="JEV Image ONLY"

def test_quantity_double_read_disagreement_must_fail_closed():
    image=synthetic()
    def fake_call(q,**_):
        reply={}
        for item in q:
            if item.key.endswith("_family"):selected="wago"
            elif item.key.endswith("_name"):selected="option_0"
            elif item.key.endswith("_second"):selected="qty_4"
            else:selected="qty_1"
            reply[item.key]=ImageAnswer(selected,.99,120,100)
        return reply
    with patch("app.modules.jev_vision_only.engine.render_pdf_pages",return_value=[image]), \
         patch("app.modules.jev_vision_only.engine.ask_images",side_effect=fake_call):
        r=analyze_pdf(b"%PDF-example","elektryka",max_marked=2,verify_quantities=True)
    assert r["quantity_crosscheck_enabled"] is True
    assert r["rows"][0]["issued"]["raw_choice"]=="qty_1"
    assert r["rows"][0]["issued"]["second_choice"]=="qty_4"
    assert r["rows"][0]["issued"]["read"] is None
    assert r["rows"][0]["issued"]["verified_agreement"] is False
    assert r["items_approved"]==0


def test_quantity_double_read_agreement_is_still_review_required():
    image=synthetic()
    def fake_call(q,**_):
        return {item.key:ImageAnswer(
            "wago" if item.key.endswith("_family") else
            "option_0" if item.key.endswith("_name") else "qty_1",
            .99,120,100) for item in q}
    with patch("app.modules.jev_vision_only.engine.render_pdf_pages",return_value=[image]), \
         patch("app.modules.jev_vision_only.engine.ask_images",side_effect=fake_call):
        r=analyze_pdf(b"%PDF-example","elektryka",max_marked=2,verify_quantities=True)
    assert r["rows"][0]["issued"]["read"]=="1"
    assert r["rows"][0]["issued"]["verified_agreement"] is True
    assert r["rows"][0]["needs_review"] is True
    assert r["coverage_complete"] is False


def test_multi_page_uncertain_layout_fails_entire_job_without_calling_api():
    image=synthetic()
    empty=np.full_like(image,255)
    with patch("app.modules.jev_vision_only.engine.render_pdf_pages",return_value=[image,empty]), \
         patch("app.modules.jev_vision_only.engine.ask_images") as api:
        result=analyze_pdf(b"%PDF-example","elektryka")
    assert result["status"]=="layout_uncertain"
    assert result["rows"]==[] and not result["coverage_complete"]
    api.assert_not_called()

def test_http_header_and_api_key_separated_from_body(monkeypatch):
    seen={}
    class Resp:
        status_code=200
        def json(self):
            return {"answers":{"q":{"choice":"one","confidence":.9}},"usage":{"input_tokens":5}}
    class Client:
        def post(self,url,headers,files,timeout):
            seen["url"]=url;seen["headers"]=headers;seen["files"]=files
            return Resp()
    monkeypatch.setenv("TYPESAFE_API_KEY","secret-test-only")
    from PIL import Image
    from io import BytesIO
    im=Image.new("RGB",(320,320),"white");buf=BytesIO();im.save(buf,format="PNG")
    result=ask_images([ImageQuestion("q",buf.getvalue(),"Read",{"one":"1"})],client=Client())
    assert result["q"].choice=="one"
    assert seen["headers"]["TypeSafe-Danger-Zone-Images"]=="true"
    import json
    body=json.loads(seen["files"]["request"][1])
    assert body["model"]=="jev-1.14.0"
    assert "secret-test-only" not in json.dumps(body)
    assert len(body["assets"])==1
