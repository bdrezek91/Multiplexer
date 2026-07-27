"""Testy Etapu 7: S3FileStorage (boto3) - zamockowane przez moto, bez sieci."""
from app.modules.documents.storage import S3FileStorage, get_storage


def test_upload_download_roundtrip(mocked_storage):
    storage = get_storage()
    storage.upload("documents/test/plik.jpg", b"zawartosc testowa", "image/jpeg")
    assert storage.download("documents/test/plik.jpg") == b"zawartosc testowa"


def test_bucket_tworzony_automatycznie_gdy_nie_istnieje(mocked_storage):
    # get_storage() samo tworzy bucket przy pierwszym uzyciu (_ensure_bucket) - jesli sie nie
    # udalo, kolejny upload rzucilby wyjatek. Test przechodzi = bucket istnieje.
    storage = S3FileStorage(None, "k", "s", "inny-bucket-testowy")
    storage.upload("a.txt", b"123", "text/plain")
    assert storage.download("a.txt") == b"123"
