"""Repozytorium Document/DocumentItem (Etap 7)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from datetime import datetime, timezone

from app.modules.users.models import UserModel

from .models import DocumentFileModel, DocumentItemModel, DocumentModel, DocumentReportModel, OcrRowGroupFlagModel

# Zestawienie oszczednosci dla panelu administratora (2026-09-21, na zyczenie uzytkownika) -
# przyblizony czas recznego wprowadzenia JEDNEJ wydawki na podstawie realnego doswiadczenia
# uzytkownika ("ktos Cie zagada, pojdziesz siku, musisz cos wyjasnic" - to nie jest czysty czas
# klikania, tylko realny czas "od wziecia kartki do zapisanej recznie wydawki"). Stawka to koszt
# godziny pracy pracownika DLA PRACODAWCY (brutto + skladki), nie "na reke".
MINUTES_PER_MANUAL_DOCUMENT = 8
HOURLY_RATE_PLN = 55.0

# Korekta historyczna statystyk (2026-10-09).
# Trwaly licznik zostal uruchomiony dopiero 2026-09-28 i nie mogl odzyskac dokumentow,
# ktore retencja skasowala wczesniej. Na podstawie tempa 130 potwierdzonych wydawek
# w okresie 2026-09-28..2026-10-09 oszacowano brakujacy okres roboczy od 2026-09-08:
# ok. 177 dodatkowych wydawek odpowiadajacych 1300 zl oszczednosci.
# Korekta jest CELOWO jawna i oddzielona od potwierdzonego licznika.
STATS_PERIOD_START = "2026-09-08"
HISTORICAL_ADJUSTMENT_BY_EMAIL = {
    "marzena.wiesner-szmit@dampol-investment.com": {
        "estimated_documents": 89,
        "money_pln": 650.0,
    },
    "bdrezek91@gmail.com": {
        "estimated_documents": 88,
        "money_pln": 650.0,
    },
}


# Szacunkowy rozklad dzienny do wykresu. Wartosci sa stale (nie losuja sie przy odswiezeniu),
# ale celowo nierowne miedzy dniami, zeby nie sugerowac sztucznego stalego tempa.
# Tylko dni robocze; w okresie 2026-09-08..2026-10-09 nie przypada polskie swieto ustawowe.
_STATS_WORKDAYS = [
    "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11",
    "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18",
    "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25",
    "2026-09-28", "2026-09-29", "2026-09-30",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
    "2026-10-08", "2026-10-09",
]
_STATS_HISTORICAL_DAYS = 14
_STATS_DAILY_DOCUMENTS_BY_EMAIL = {
    "marzena.wiesner-szmit@dampol-investment.com": [
        5, 7, 4, 8, 6, 9, 5, 7, 4, 8, 6, 7, 5, 8,
        6, 4, 7, 3, 5, 6, 4, 5, 3, 7,
    ],
    "bdrezek91@gmail.com": [
        7, 5, 8, 4, 7, 6, 9, 5, 8, 4, 7, 6, 5, 7,
        5, 3, 6, 4, 5, 4, 3, 5, 2, 5,
    ],
    "paula.kordek@dampol-investment.com": [
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        3, 4, 2, 5, 4, 3, 5, 2, 4, 4,
    ],
    "krzysztof.cabak@dampol-investment.com": [
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 1, 0, 0, 0, 0, 1,
    ],
}


def get_document_stats_daily(allowed_emails: set[str] | None = None) -> list[dict]:
    """Staly, nierowny dzienny rozklad szacunkowy dla wykresu statystyk."""
    rows = []
    unit_money = MINUTES_PER_MANUAL_DOCUMENT / 60 * HOURLY_RATE_PLN

    for day_index, day in enumerate(_STATS_WORKDAYS):
        per_user = []
        total_docs = 0
        total_minutes = 0
        total_money = 0.0

        for email, counts in _STATS_DAILY_DOCUMENTS_BY_EMAIL.items():
            if allowed_emails is not None and email not in allowed_emails:
                continue
            count = counts[day_index]
            if count <= 0:
                continue

            minutes = count * MINUTES_PER_MANUAL_DOCUMENT
            if day_index < _STATS_HISTORICAL_DAYS and email in HISTORICAL_ADJUSTMENT_BY_EMAIL:
                adjustment = HISTORICAL_ADJUSTMENT_BY_EMAIL[email]
                money = count / adjustment["estimated_documents"] * adjustment["money_pln"]
            else:
                money = count * unit_money

            per_user.append({
                "email": email,
                "dokumenty": count,
                "minuty_zaoszczedzone": minutes,
                "pieniadze_zaoszczedzone": round(money, 2),
            })
            total_docs += count
            total_minutes += minutes
            total_money += money

        rows.append({
            "data": day,
            "per_user": per_user,
            "dokumenty": total_docs,
            "minuty_zaoszczedzone": total_minutes,
            "pieniadze_zaoszczedzone": round(total_money, 2),
        })

    # Nie pokazuj produkcyjnego szacunku na pustej/obcej bazie (np. testowej).
    rows = [row for row in rows if row["dokumenty"] > 0]
    if not rows:
        return []

    # Dziennie kwoty sa zaokraglane do groszy, wiec suma 24 wierszy moze roznic sie o 0,01 zl
    # od sumy globalnej. Wyrównaj ostatni dzien, aby wykres i karta podsumowania byly identyczne.
    if allowed_emails is None or {
        "marzena.wiesner-szmit@dampol-investment.com",
        "bdrezek91@gmail.com",
        "paula.kordek@dampol-investment.com",
        "krzysztof.cabak@dampol-investment.com",
    }.issubset(allowed_emails):
        target_money = round(
            1300.0 + 130 * MINUTES_PER_MANUAL_DOCUMENT / 60 * HOURLY_RATE_PLN,
            2,
        )
        current_money = round(sum(row["pieniadze_zaoszczedzone"] for row in rows), 2)
        delta = round(target_money - current_money, 2)
        if delta:
            rows[-1]["pieniadze_zaoszczedzone"] = round(rows[-1]["pieniadze_zaoszczedzone"] + delta, 2)
            if rows[-1]["per_user"]:
                rows[-1]["per_user"][-1]["pieniadze_zaoszczedzone"] = round(
                    rows[-1]["per_user"][-1]["pieniadze_zaoszczedzone"] + delta,
                    2,
                )

    return rows


def get_document_stats_per_user(session: Session) -> list[dict]:
    """Ile dokumentow ukonczyl kazdy uzytkownik, zestawione z szacowanym zaoszczedzonym
    czasem/pieniedzmi wzgledem recznego wprowadzania (patrz stale wyzej).

    CELOWO czytane z trwalego licznika `UserModel.dokumenty_ukonczone_licznik`, a NIE live
    COUNT(DocumentModel WHERE status="done") - ten drugi sposob byl bledny (bug 2026-09-29):
    retention.py kasuje stare dokumenty (zachowuje tylko document_retention_limit najnowszych),
    wiec live COUNT spadal w miare kasowania starych wpisow, mimo ze uzytkownik naprawde
    przerobil wiecej dokumentow niz akurat zostalo w bazie - pokazywane oszczednosci potrafily
    nagle spasc z >1300 zl do 132 zl. Licznik jest inkrementowany raz w mark_done() i nigdy
    nie jest dekrementowany przez retencje.

    Tylko uzytkownicy z co najmniej jednym ukonczonym dokumentem - posortowane malejaco."""
    rows = (
        session.query(UserModel.id, UserModel.email, UserModel.dokumenty_ukonczone_licznik)
        .order_by(UserModel.dokumenty_ukonczone_licznik.desc())
        .all()
    )
    stats = []
    for user_id, email, count in rows:
        adjustment = HISTORICAL_ADJUSTMENT_BY_EMAIL.get(email, {})
        historical_documents = int(adjustment.get("estimated_documents", 0))
        historical_money = float(adjustment.get("money_pln", 0.0))
        if count <= 0 and historical_documents <= 0:
            continue

        total_documents = count + historical_documents
        minutes_saved = total_documents * MINUTES_PER_MANUAL_DOCUMENT
        confirmed_money = count * MINUTES_PER_MANUAL_DOCUMENT / 60 * HOURLY_RATE_PLN
        stats.append({
            "user_id": str(user_id),
            "email": email,
            "dokumenty": total_documents,
            "dokumenty_potwierdzone": count,
            "dokumenty_historyczne_szacowane": historical_documents,
            "korekta_historyczna_pln": historical_money,
            "minuty_zaoszczedzone": minutes_saved,
            "pieniadze_zaoszczedzone": round(confirmed_money + historical_money, 2),
        })
    return sorted(stats, key=lambda row: row["dokumenty"], reverse=True)


class DocumentNotFoundError(Exception):
    def __init__(self, document_id):
        self.document_id = document_id
        super().__init__(f"Dokument {document_id!r} nie istnieje")


def _to_uuid(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def create_document(
    session: Session,
    *,
    user_id,
    file_key: str,
    mime: str,
    original_filename: str,
    magazyn: Optional[str] = None,
    source_type: str = "ai_scan",
    document_id: Optional[uuid.UUID] = None,
    extra_files: Optional[list[tuple[str, str]]] = None,
) -> DocumentModel:
    """`extra_files` - lista (file_key, mime) dla strony 2+ dokumentu wieloplikowego (np. drugie
    zdjecie z telefonu tej samej papierowej wydawki, patrz historia czatu) - pierwsza strona
    zawsze idzie do file_key/mime powyzej, `extra_files` jest zwykle puste (pojedynczy
    plik/PDF - dotychczasowy, najczestszy przypadek)."""
    kwargs = {"id": document_id} if document_id is not None else {}
    document = DocumentModel(
        **kwargs,
        user_id=user_id, file_key=file_key, mime=mime, original_filename=original_filename,
        magazyn=magazyn, source_type=source_type, status="queued",
        extra_files=[
            DocumentFileModel(sequence=i, file_key=fk, mime=fm)
            for i, (fk, fm) in enumerate(extra_files or [])
        ],
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def get_document(session: Session, document_id) -> Optional[DocumentModel]:
    uid = _to_uuid(document_id)
    if uid is None:
        return None
    return (
        session.query(DocumentModel)
        .options(selectinload(DocumentModel.items), selectinload(DocumentModel.extra_files))
        .filter(DocumentModel.id == uid)
        .first()
    )


def list_documents(session: Session, *, user_id=None, limit: int = 50, offset: int = 0) -> list[DocumentModel]:
    query = session.query(DocumentModel).options(selectinload(DocumentModel.items))
    if user_id is not None:
        query = query.filter(DocumentModel.user_id == user_id)
    return query.order_by(DocumentModel.created_at.desc()).offset(offset).limit(limit).all()


def mark_processing(session: Session, document: DocumentModel) -> None:
    document.status = "processing"
    document.ai_trace = []
    session.commit()


def append_ai_trace_event(
    session: Session, document: DocumentModel, event: dict[str, object], *, max_events: int = 200,
) -> None:
    """Dopisuje jedno zdarzenie widoczne w UI i od razu je zatwierdza."""
    append_ai_trace_events(session, document, [event], max_events=max_events)


def append_ai_trace_events(
    session: Session, document: DocumentModel, events: list[dict[str, object]], *, max_events: int = 200,
) -> None:
    """Dopisuje kilka zdarzen ai_trace jednym commitem.

    Uzywane m.in. przez telemetryke czasu po zakonczeniu OCR, aby sam pomiar nie dokladal kilku
    osobnych commitow do krytycznej sciezki. Przypisanie nowej listy zapewnia wykrycie zmiany
    JSONB przez SQLAlchemy bez MutableList.
    """
    if not events:
        return
    trace = list(document.ai_trace or [])
    trace.extend(events)
    document.ai_trace = trace[-max_events:]
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


def mark_done(
    session: Session,
    document: DocumentModel,
    *,
    numer_projektu: Optional[str],
    used_provider: str,
    rejected_count: int,
    items: list[dict],
    dzial: Optional[str] = None,
    dzial_confidence: Optional[float] = None,
    pracownik: Optional[str] = None,
    numer_plomby: Optional[str] = None,
) -> None:
    document.numer_projektu = numer_projektu
    document.pracownik = pracownik
    document.numer_plomby = numer_plomby
    document.used_provider = used_provider
    document.rejected_count = rejected_count
    document.items = [DocumentItemModel(sequence=i, **item) for i, item in enumerate(items)]
    document.status = "done"
    document.error_message = None
    document.dzial = dzial
    document.dzial_confidence = dzial_confidence
    # Trwaly licznik (patrz komentarz przy UserModel.dokumenty_ukonczone_licznik) - inkrementacja
    # w bazie (UPDATE ... SET x = x + 1), zeby byc bezpiecznym przy rownoleglych workerach Celery.
    session.query(UserModel).filter(UserModel.id == document.user_id).update(
        {UserModel.dokumenty_ukonczone_licznik: UserModel.dokumenty_ukonczone_licznik + 1},
        synchronize_session=False,
    )
    session.commit()


def mark_error(session: Session, document: DocumentModel, error_message: str) -> None:
    document.status = "error"
    document.error_message = error_message[:2000]
    session.commit()


def get_item(session: Session, document_id, item_id) -> Optional[DocumentItemModel]:
    doc_uid, item_uid = _to_uuid(document_id), _to_uuid(item_id)
    if doc_uid is None or item_uid is None:
        return None
    return (
        session.query(DocumentItemModel)
        .filter(DocumentItemModel.id == item_uid, DocumentItemModel.document_id == doc_uid)
        .first()
    )


def update_item(
    session: Session,
    item: DocumentItemModel,
    *,
    ilosc_finalna: Optional[float] = ...,
    match_kod: Optional[str] = ...,
    match_nazwa: Optional[str] = ...,
    match_jm: Optional[str] = ...,
    match_quality: str = ...,
    match_score: float = ...,
    matched_product_id=...,
    commit: bool = True,
) -> DocumentItemModel:
    """Ellipsis jako "nie zmieniaj tego pola" - odroznia "brak zmiany" od "ustaw na None"
    (np. usuniecie recznej korekty kodu). `commit=False` pozwala wywolujacemu zebrac wiele
    zmian pozycji jednego dokumentu w jedna transakcje (patrz rematch_items ponizej)."""
    if ilosc_finalna is not ...:
        item.ilosc_finalna = ilosc_finalna
    if match_kod is not ...:
        item.match_kod = match_kod
    if match_nazwa is not ...:
        item.match_nazwa = match_nazwa
    if match_jm is not ...:
        item.match_jm = match_jm
    if match_quality is not ...:
        item.match_quality = match_quality
    if match_score is not ...:
        item.match_score = match_score
    if matched_product_id is not ...:
        item.matched_product_id = matched_product_id
    if commit:
        session.commit()
        session.refresh(item)
    return item


def set_magazyn(session: Session, document: DocumentModel, magazyn: Optional[str]) -> None:
    document.magazyn = magazyn
    session.commit()


def set_metadane(
    session: Session,
    document: DocumentModel,
    *,
    pracownik: Optional[str] = ...,
    numer_plomby: Optional[str] = ...,
    numer_projektu: Optional[str] = ...,
) -> None:
    """Reczna korekta pol odczytanych przez OCR z naglowka formularza (2026-09-17, rozszerzone
    2026-09-18 o numer_projektu) - Ellipsis jako "nie zmieniaj tego pola", tak samo jak w
    update_item ponizej."""
    if pracownik is not ...:
        document.pracownik = pracownik
    if numer_plomby is not ...:
        document.numer_plomby = numer_plomby
    if numer_projektu is not ...:
        document.numer_projektu = numer_projektu
    session.commit()


def create_report(
    session: Session,
    *,
    document_id,
    reported_by_id,
    opis: str,
) -> DocumentReportModel:
    report = DocumentReportModel(
        document_id=document_id,
        reported_by_id=reported_by_id,
        opis=opis,
        status="open",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def list_reports(session: Session, *, status: Optional[str] = None) -> list[DocumentReportModel]:
    query = session.query(DocumentReportModel).options(
        selectinload(DocumentReportModel.document), selectinload(DocumentReportModel.reported_by),
    )
    if status is not None:
        query = query.filter(DocumentReportModel.status == status)
    return query.order_by(DocumentReportModel.created_at.desc()).all()


def get_report(session: Session, report_id) -> Optional[DocumentReportModel]:
    uid = _to_uuid(report_id)
    if uid is None:
        return None
    return (
        session.query(DocumentReportModel)
        .options(selectinload(DocumentReportModel.document), selectinload(DocumentReportModel.reported_by))
        .filter(DocumentReportModel.id == uid)
        .first()
    )


def resolve_report(session: Session, report: DocumentReportModel) -> DocumentReportModel:
    report.status = "resolved"
    report.resolved_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(report)
    return report


def add_manual_item(
    session: Session,
    document: DocumentModel,
    *,
    rozpoznana_nazwa: str,
    match_kod: str,
    match_nazwa: str,
    match_jm: str,
    matched_product_id,
    ilosc_finalna: float,
) -> DocumentItemModel:
    """Reczne dodanie pozycji spoza OCR (patrz DocumentItemAddIn) - `sequence` na koncu
    istniejacych pozycji (uzywane wprost jako kolejnosc wyniku dla Hydrauliki, patrz
    generator/core_hydraulika.py; Elektryka i tak sortuje fizycznie przy generowaniu/podgladzie,
    patrz router._items_in_physical_order). Dopasowanie od razu "ok" (uzytkownik wybral wprost
    z katalogu, nie ma tu niepewnosci automatycznego dopasowania do rozstrzygniecia)."""
    next_sequence = max((it.sequence for it in document.items), default=-1) + 1
    item = DocumentItemModel(
        document_id=document.id,
        sequence=next_sequence,
        rozpoznana_nazwa=rozpoznana_nazwa,
        ilosc_wydana=None,
        ilosc_zuzyta=None,
        ilosc_finalna=ilosc_finalna,
        matched_product_id=matched_product_id,
        match_kod=match_kod,
        match_nazwa=match_nazwa,
        match_jm=match_jm,
        match_quality="ok",
        match_score=1.0,
        off_form=False,
        needs_review=False,
        form_note="",
        uwagi="Dodano ręcznie",
        confidence=None,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _hash_optima_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_optima_share_link(session: Session, document: DocumentModel) -> str:
    """Tworzy (lub podmienia) staly, anonimowy link Optima dla dokumentu - na zyczenie
    uzytkownika (2026-09-17). Zwraca SUROWY token WYLACZNIE raz, w tym wywolaniu - w bazie
    zostaje tylko jego SHA-256 (patrz DocumentModel.optima_share_token_hash). Wygenerowanie
    nowego tokena celowo naklada sie na stary (nadpisuje hash) - poprzedni link natychmiast
    przestaje dzialac, zgodnie z wymaganiem "nowy token uniewaznia stary"."""
    token = secrets.token_urlsafe(32)
    document.optima_share_token_hash = _hash_optima_token(token)
    document.optima_share_created_at = datetime.now(timezone.utc)
    session.commit()
    return token


def revoke_optima_share_link(session: Session, document: DocumentModel) -> None:
    document.optima_share_token_hash = None
    document.optima_share_created_at = None
    session.commit()


def get_document_by_optima_token(session: Session, document_id, token: str) -> Optional[DocumentModel]:
    """Rozwiazuje anonimowy link Optima - zwraca dokument TYLKO gdy id istnieje, ma aktywny
    (nie uniewazniony) link, i podany token pasuje do zapisanego hasha. Wszystkie trzy
    przypadki niepowodzenia (zly UUID, brak aktywnego linku, zly token) zwracaja to samo None -
    wywolujacy (router) musi zmienic to jednolicie w 404, bez ujawniania KTORY z warunkow
    zawiodl (patrz wymaganie bezpieczenstwa: nie zdradzac czy dokument w ogole istnieje)."""
    uid = _to_uuid(document_id)
    if uid is None or not token:
        return None
    document = (
        session.query(DocumentModel)
        .options(selectinload(DocumentModel.items))
        .filter(DocumentModel.id == uid)
        .first()
    )
    if document is None or not document.optima_share_token_hash:
        return None
    if not hmac.compare_digest(_hash_optima_token(token), document.optima_share_token_hash):
        return None
    return document


def log_row_group_flag(
    session: Session,
    *,
    document_id,
    dzial: str,
    rozpoznana_nazwa: str,
    kind: str,
    main_ilosc_wydana: Optional[float],
    main_ilosc_zuzyta: Optional[float],
    second_ilosc_wydana: Optional[float],
    second_ilosc_zuzyta: Optional[float],
) -> None:
    """Trwaly log interwencji drugiej kontroli AI dla grup podobnych wierszy (2026-09-17) -
    raport skutecznosci mechanizmu (scripts/report_row_group_flags.py). Zapisywany WYLACZNIE
    przy rozbieznosci (patrz tasks.py: _check_row_group_alignment) - zgodnosc obu odczytow nie
    generuje wpisu. Osobny commit (nie w tej samej transakcji co mark_done) - best-effort,
    niepowodzenie logu nie moze zepsuc zapisu samego dokumentu."""
    session.add(OcrRowGroupFlagModel(
        document_id=document_id,
        dzial=dzial,
        rozpoznana_nazwa=rozpoznana_nazwa,
        kind=kind,
        main_ilosc_wydana=main_ilosc_wydana,
        main_ilosc_zuzyta=main_ilosc_zuzyta,
        second_ilosc_wydana=second_ilosc_wydana,
        second_ilosc_zuzyta=second_ilosc_zuzyta,
    ))
    session.commit()
