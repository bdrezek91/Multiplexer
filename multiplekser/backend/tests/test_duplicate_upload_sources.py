"""Identical multipart uploads never duplicate OCR lines or material quantities."""
import hashlib
import pytest
from app.modules.documents import ocr_processing

class MemoryStorage:
    def __init__(self,files):
        self.files=files
        self.downloads=[]
    def download(self,key):
        self.downloads.append(key)
        return self.files[key]


def test_same_pdf_bytes_two_keys_only_prepare_once(monkeypatch):
    pdf=b'%PDF-1.7\nSAME SCAN, TWO PAGES'
    store=MemoryStorage({'001-scan.pdf':pdf,'002-scan.pdf':pdf})
    calls=[]
    def prepare(blob,mime):
        calls.append((blob,mime))
        return [(b'page1','image/jpeg'),(b'page2','image/jpeg')]
    monkeypatch.setattr(ocr_processing,'_prepare_source_bytes',prepare)
    pages,skipped=ocr_processing._prepare_distinct_sources(lambda:store,
        [('001-scan.pdf','application/pdf'),('002-scan.pdf','application/pdf')])
    assert pages==[(b'page1','image/jpeg'),(b'page2','image/jpeg')]
    assert skipped==1 and len(calls)==1
    assert store.downloads==['001-scan.pdf','002-scan.pdf']


def test_distinct_pages_preserved_even_if_extension_identical(monkeypatch):
    store=MemoryStorage({'first.jpg':b'ONE','second.jpg':b'TWO'})
    monkeypatch.setattr(ocr_processing,'_prepare_source_bytes',lambda raw,mime:[(raw,mime)])
    files,skipped=ocr_processing._prepare_distinct_sources(lambda:store,
        [('first.jpg','image/jpeg'),('second.jpg','image/jpeg')])
    assert skipped==0
    assert files==[(b'ONE','image/jpeg'),(b'TWO','image/jpeg')]


def test_duplicates_not_only_consecutive(monkeypatch):
    store=MemoryStorage({'a':b'ONE','b':b'TWO','c':b'ONE'})
    monkeypatch.setattr(ocr_processing,'_prepare_source_bytes',lambda raw,mime:[(raw,mime)])
    files,skipped=ocr_processing._prepare_distinct_sources(lambda:store,
        [('a','image/jpeg'),('b','image/jpeg'),('c','image/jpeg')])
    assert skipped==1
    assert files==[(b'ONE','image/jpeg'),(b'TWO','image/jpeg')]


def test_dedup_never_discards_different_raw_files_same_filename(monkeypatch):
    store=MemoryStorage({'folder1/photo.jpg':b'PAGE-1','folder2/photo.jpg':b'PAGE-2'})
    monkeypatch.setattr(ocr_processing,'_prepare_source_bytes',lambda raw,mime:[(raw,mime)])
    files,skipped=ocr_processing._prepare_distinct_sources(lambda:store,
        [('folder1/photo.jpg','image/jpeg'),('folder2/photo.jpg','image/jpeg')])
    assert skipped==0 and len(files)==2


def test_prepare_exception_is_not_hidden(monkeypatch):
    store=MemoryStorage({'bad':b'CORRUPT','good':b'OK'})
    def prepare(raw,mime):
        if raw==b'CORRUPT':raise ValueError('invalid PDF')
        return [(raw,mime)]
    monkeypatch.setattr(ocr_processing,'_prepare_source_bytes',prepare)
    with pytest.raises(ValueError,match='invalid PDF'):
        ocr_processing._prepare_distinct_sources(lambda:store,
            [('bad','application/pdf'),('good','image/jpeg')])
