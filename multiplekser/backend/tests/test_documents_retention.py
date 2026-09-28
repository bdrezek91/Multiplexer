from datetime import datetime, timedelta, timezone

from app.modules.documents import repository
from app.modules.documents.models import DocumentModel, OcrRowGroupFlagModel
from app.modules.documents.retention import prune_documents
from app.modules.documents.storage import get_storage


def test_retention_keeps_latest_20_and_protects_processing(
    db_session, admin_user, mocked_storage,
):
    storage = get_storage()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    documents = []

    for index in range(24):
        key = f"documents/retention/{index:03d}.jpg"
        storage.upload(key, f"file-{index}".encode(), "image/jpeg")
        document = repository.create_document(
            db_session,
            user_id=admin_user.id,
            file_key=key,
            mime="image/jpeg",
            original_filename=f"{index:03d}.jpg",
        )
        document.created_at = base + timedelta(minutes=index)
        document.status = "processing" if index == 0 else "done"
        db_session.commit()
        documents.append(document)

    removed = prune_documents(db_session, storage, limit=20)

    assert removed == 3
    assert db_session.query(DocumentModel).count() == 21
    assert repository.get_document(db_session, documents[0].id).status == "processing"
    assert repository.get_document(db_session, documents[1].id) is None
    assert repository.get_document(db_session, documents[2].id) is None
    assert repository.get_document(db_session, documents[3].id) is None
    assert repository.get_document(db_session, documents[4].id) is not None


def _make_old_documents(db_session, admin_user, storage, count: int, base=None):
    base = base or datetime(2026, 1, 1, tzinfo=timezone.utc)
    documents = []
    for index in range(count):
        key = f"documents/retention-reports/{index:03d}.jpg"
        storage.upload(key, f"file-{index}".encode(), "image/jpeg")
        document = repository.create_document(
            db_session, user_id=admin_user.id, file_key=key, mime="image/jpeg",
            original_filename=f"{index:03d}.jpg",
        )
        document.created_at = base + timedelta(minutes=index)
        document.status = "done"
        db_session.commit()
        documents.append(document)
    return documents


def test_retention_nie_usuwa_dokumentu_z_nierozwiazanym_zgloszeniem(
    db_session, admin_user, mocked_storage,
):
    """Na zyczenie uzytkownika (2026-09-28): zgloszenie problemu od pracownika musi zostac
    dostepne do rozwiazania, niezaleznie jak stary jest dokument - retencja nie moze go usunac,
    dopoki admin nie oznaczy zgloszenia jako rozwiazane."""
    storage = get_storage()
    documents = _make_old_documents(db_session, admin_user, storage, 22)
    reported = documents[0]  # najstarszy - normalnie pierwszy kandydat do usuniecia
    repository.create_report(
        db_session, document_id=reported.id, reported_by_id=admin_user.id, opis="Zle dopasowanie",
    )

    removed = prune_documents(db_session, storage, limit=20)

    assert removed == 1  # tylko documents[1] usuniety, documents[0] chroniony mimo bycia starszym
    assert repository.get_document(db_session, reported.id) is not None
    assert repository.get_document(db_session, documents[1].id) is None


def test_retention_usuwa_dokument_po_rozwiazaniu_zgloszenia(
    db_session, admin_user, mocked_storage,
):
    storage = get_storage()
    documents = _make_old_documents(db_session, admin_user, storage, 21)
    reported = documents[0]
    report = repository.create_report(
        db_session, document_id=reported.id, reported_by_id=admin_user.id, opis="Zle dopasowanie",
    )
    repository.resolve_report(db_session, report)

    removed = prune_documents(db_session, storage, limit=20)

    assert removed == 1
    assert repository.get_document(db_session, reported.id) is None


def test_retention_jeden_zablokowany_dokument_nie_psuje_reszty_paczki(
    db_session, admin_user, mocked_storage,
):
    """Regresja realnego bledu produkcyjnego (2026-09-28): dokument z powiazanym wpisem
    ocr_row_group_flag (log drugiej kontroli AI) bez kaskadowego usuwania wywalal
    IntegrityError, ktory wczesniej wybijal CALA paczke (session.commit() na samym koncu petli) -
    retencja po cichu nie usuwala WTEDY NIC. Teraz kazdy dokument jest commitowany osobno, wiec
    jeden problematyczny wiersz nie blokuje usuniecia pozostalych."""
    storage = get_storage()
    documents = _make_old_documents(db_session, admin_user, storage, 25)
    flagged = documents[0]
    db_session.add(OcrRowGroupFlagModel(
        document_id=flagged.id, dzial="elektryka", rozpoznana_nazwa="Test",
        kind="full_reread_mismatch",
    ))
    db_session.commit()

    removed = prune_documents(db_session, storage, limit=20)

    # 5 dokumentow ponad limit, w tym "flagged" - kaskada teraz pozwala go usunac razem z logiem.
    assert removed == 5
    assert repository.get_document(db_session, flagged.id) is None


def test_retention_usuwa_wiersz_nawet_gdy_usuniecie_pliku_zawiedzie(
    db_session, admin_user, mocked_storage, monkeypatch,
):
    """Regresja drugiej czesci naprawy z 2026-09-28 (znalezionej podczas analizy prawdziwej
    przyczyny dokumentow bez pliku na produkcji - patrz historia czatu: to NIE byl reset
    wolumenu/restart, tylko ten sam blad retencji): kolejnosc MUSI byc "wiersz najpierw, plik
    potem". Stary kod kasowal PLIK przed commitem wiersza - gdy commit z jakiegokolwiek powodu
    zawodzil, plik znikal bezpowrotnie a wiersz zostawal (dokladnie objaw zgloszony przez
    uzytkownika: "nie znaleziono w storage"). Test symuluje odwrotna, bezpieczna sytuacje:
    usuniecie PLIKU zawodzi (np. przejsciowy blad sieci do MinIO) - dokument i tak znika z bazy,
    plik zostaje tylko osierocony (nieszkodliwe: dokumentu juz nie ma w UI)."""
    storage = get_storage()
    documents = _make_old_documents(db_session, admin_user, storage, 21)
    doomed = documents[0]

    original_delete = storage.delete

    def failing_delete(key):
        if key == doomed.file_key:
            raise RuntimeError("symulowana przejsciowa awaria sieci do MinIO")
        return original_delete(key)

    monkeypatch.setattr(storage, "delete", failing_delete)

    removed = prune_documents(db_session, storage, limit=20)

    assert removed == 1
    assert repository.get_document(db_session, doomed.id) is None
