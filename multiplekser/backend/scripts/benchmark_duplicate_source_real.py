"""Read-only verification of duplicate source content before any production rollout."""
import argparse
import time
from sqlalchemy import text
from app.core.db import engine
from app.modules.documents.storage import get_storage
from app.modules.documents.ocr_processing import _download_and_prepare, _prepare_distinct_sources

p=argparse.ArgumentParser()
p.add_argument('--document',required=True,help='One completed document with known duplicate uploads')
DOC=p.parse_args().document
with engine.connect() as con:
    first=con.execute(text('SELECT file_key,mime FROM document WHERE id=:id'),{'id':DOC}).one()
    extras=con.execute(text('SELECT file_key,mime FROM document_file WHERE document_id=:id ORDER BY sequence'),{'id':DOC}).all()
    sources=[tuple(first)]+[tuple(a) for a in extras]
started=time.perf_counter()
unique,skipped=_prepare_distinct_sources(get_storage,sources)
t1=time.perf_counter()
first_only=_download_and_prepare(get_storage,first[0],first[1])
assert skipped==1 and len(unique)==len(first_only)==2
assert unique==first_only
print('DEDUP_REAL_OK','sources',len(sources),'skipped_exact_duplicates',skipped,
      'images',len(unique),'identical_to_original_first_upload',unique==first_only,
      'dedup_preparation_s',round(t1-started,3),'single_preparation_s',round(time.perf_counter()-t1,3),flush=True)
