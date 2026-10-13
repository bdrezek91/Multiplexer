"""AUTO FAST: PDF speedup must preserve order, bytes and blank-page safety."""
import pytest
from app.modules.documents import ocr_processing as target


class Storage:
    def download(self, key):
        return b"fake-pdf"


def test_fast_pdf_preserves_images_order_and_skips_only_blank(monkeypatch):
    monkeypatch.setattr(target,"pdf_to_page_images",lambda blob:[b"page1",b"blank",b"page3"])
    monkeypatch.setattr(target,"is_blank_page",lambda img:img==b"blank")
    monkeypatch.setattr(target,"downscale_image",lambda img:b"jpeg:"+img)
    original_threads=target.cv2.getNumThreads()
    result=target._download_and_prepare(Storage,"key","application/pdf")
    assert result==[(b"jpeg:page1","image/jpeg"),(b"jpeg:page3","image/jpeg")]
    assert target.cv2.getNumThreads()==original_threads


def test_fast_pdf_retains_all_pages_if_every_page_is_blank(monkeypatch):
    monkeypatch.setattr(target,"pdf_to_page_images",lambda blob:[b"blank1",b"blank2"])
    monkeypatch.setattr(target,"is_blank_page",lambda img:True)
    monkeypatch.setattr(target,"downscale_image",lambda img:b"jpeg:"+img)
    assert target._download_and_prepare(Storage,"key","application/pdf")==[
        (b"jpeg:blank1","image/jpeg"),(b"jpeg:blank2","image/jpeg")]


def test_single_page_keeps_original_path(monkeypatch):
    monkeypatch.setattr(target,"pdf_to_page_images",lambda blob:[b"one"])
    monkeypatch.setattr(target,"is_blank_page",lambda img:False)
    monkeypatch.setattr(target,"downscale_image",lambda img:b"jpeg:"+img)
    assert target._download_and_prepare(Storage,"key","application/pdf")==[(b"jpeg:one","image/jpeg")]


def test_fast_pdf_restores_cv2_threads_on_exception(monkeypatch):
    monkeypatch.setattr(target,"pdf_to_page_images",lambda blob:[b"p1",b"p2"])
    monkeypatch.setattr(target,"is_blank_page",lambda img:False)
    monkeypatch.setattr(target,"downscale_image",lambda img:(_ for _ in ()).throw(ValueError("bad image")))
    original_threads=target.cv2.getNumThreads()
    with pytest.raises(ValueError,match="bad image"):
        target._download_and_prepare(Storage,"key","application/pdf")
    assert target.cv2.getNumThreads()==original_threads
