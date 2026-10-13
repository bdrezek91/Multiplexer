"""Multiplekser V3 AUTO: classify department from literal OCR labels + header evidence.

Claude may read the printed header, but it never chooses product codes. Never
silently choose a warehouse catalog on contradictory or absent evidence.
"""
from __future__ import annotations
import re
import unicodedata

ELECTRIC = (
    r"\b(?:gniazdo|gniazdka|wylacznik|bezpiecznik|rozdzielnia|wtyczka|"
    r"przewod|kabel|kostka elektryczna|oprawa|stycznik|zarowka|led|"
    r"zasilacz|puszka instalacyjna|peszel|lacznik schodowy)\b"
)
HYDRAULIC = (
    r"\b(?:kolanko|trojnik|rura|syfon|kompakt wc|umywalk|bateria umywalk|"
    r"zawor|zlew|kabina prysznic|bojler|odplyw|waz prysznic|"
    r"mufa|redukcja kanaliz|uszczelka hydraul|listwa boczna aluminiowa|"
    r"koncowka bezowa|przylacze wody)\b"
)
_PATTERNS = {
    "elektryka": re.compile(ELECTRIC, re.IGNORECASE),
    "hydraulika": re.compile(HYDRAULIC, re.IGNORECASE),
}


class AmbiguousDepartment(ValueError):
    pass


def _plain(value: str) -> str:
    value=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii")
    return re.sub(r"\s+"," ",value.casefold()).strip()


def classify_auto_dzial(rows: list[dict]) -> tuple[str,float,str]:
    """Return (department, confidence 0..100, method).

    The classifier does not use code predictions from any LLM. Ambiguity means
    stop with a reviewable error rather than silently mismatching catalogs.
    """
    votes={"elektryka":0,"hydraulika":0}
    names=(_plain(row.get("nazwa","")) for row in rows)
    for name in names:
        for department, pattern in _PATTERNS.items():
            if pattern.search(name):
                votes[department]+=1

    hints=[
        row.get("_dzial_hint") for row in rows
        if row.get("_dzial_hint") in {"elektryka","hydraulika"}
    ]
    header=max(set(hints), key=hints.count) if hints else None
    if len(set(hints))>1 and min(hints.count("elektryka"),hints.count("hydraulika"))>=2:
        raise AmbiguousDepartment("Niejednoznaczny dział w nagłówkach skanu")

    if header:
        opposite="hydraulika" if header=="elektryka" else "elektryka"
        if votes[opposite]>=3 and votes[opposite]>votes[header]*2:
            raise AmbiguousDepartment(
                "Nagłówek wskazuje inny dział niż materiały; sprawdź wydawkę ręcznie"
            )
        return header,96.0 if votes[header]>=2 else 82.0,"nagłówek Claude + słownik"

    winner=max(votes,key=votes.get)
    loser="hydraulika" if winner=="elektryka" else "elektryka"
    if votes[winner]>=3 and votes[winner]>=votes[loser]*3:
        return winner,77.0,"słownik nazw materiałów"
    raise AmbiguousDepartment(
        "Nie udało się jednoznacznie ustalić działu. Otwórz diagnostykę i wybierz go ręcznie."
    )


def _normalise_match(name: str) -> str:
    return re.sub(r"[^a-z0-9]+"," ",_plain(name)).strip()


def reconcile_verify_rows(
    suspect: list[tuple[dict,object]],
    rechecked: list[dict],
) -> tuple[int,int]:
    """Second opinion ONLY; never silently overwrite issued/consumed quantities.

    A unique matching row with exactly identical separate quantity columns
    counts as confirmation. Conflicts stay flagged for human review.
    """
    candidates={}
    for row in rechecked:
        key=(_normalise_match(row["nazwa"]),int(row.get("page_number") or 1))
        candidates.setdefault(key,[]).append(row)
    confirmed=0
    conflicts=0
    for first,position in suspect:
        key=(_normalise_match(first["nazwa"]),int(first.get("page_number") or 1))
        matches=candidates.get(key,[])
        original_qty=(
            str(first.get("ilosc_wydana") or ""),
            str(first.get("ilosc_zuzyta") or "")
        )
        if len(matches)!=1:
            conflicts+=1
            position.form_note=(position.form_note or "")+" Opus: nie znalazł jednoznacznie wiersza."
            continue
        other=matches[0]
        verified_qty=(
            str(other.get("ilosc_wydana") or ""),
            str(other.get("ilosc_zuzyta") or ""),
        )
        if original_qty==verified_qty:
            confirmed+=1
            position.form_note=(position.form_note or "")+" Opus potwierdził obie ilości."
            if not position.off_form and position.match.quality != "bad":
                position.needs_review=False
        else:
            conflicts+=1
            position.needs_review=True
            position.form_note=(position.form_note or "")+(
                f" AUTO: Claude={original_qty[0]}/{original_qty[1]}, "
                f"Opus={verified_qty[0]}/{verified_qty[1]}. Sprawdź skan!"
            )
    return confirmed,conflicts


def recognize_with_free_gemini(files, session, magazyn):
    """Quota fallback: free Gemini only. Never chain into paid keys/OpenAI API."""
    import asyncio
    from app.core.config import settings
    from app.modules.ocr.classify import classify_document
    from app.modules.ocr.chain import classify_ocr_chain, background_verification_chain
    from app.modules.ocr.pipeline_elektryka import recognize_document
    from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
    from app.modules.ocr.image import classification_header_preview
    from app.modules.matcher import rules_from_db
    from app.modules.products import Catalog

    if not settings.gemini_api_key_free:
        raise RuntimeError("Brak darmowego klucza Gemini; nie wolno użyć płatnej ścieżki")
    free_classify=[step for step in classify_ocr_chain()
                   if "darmowy" in step.label and step.api_key==settings.gemini_api_key_free]
    classify=asyncio.run(classify_document(
        [(classification_header_preview(files[0][0]),"image/jpeg")],
        chain=free_classify,
    ))
    if classify.fallback or classify.confidence<65:
        raise AmbiguousDepartment("Darmowy Gemini nie potwierdził działu; sprawdź ręcznie")
    dzial=classify.dzial
    cat=Catalog.from_db(session,dzial=dzial)
    steps=[step for step in background_verification_chain()
           if "darmowy" in step.label and step.api_key==settings.gemini_api_key_free]
    if not steps:
        raise RuntimeError("Brak darmowych modeli Gemini")
    if dzial=="hydraulika":
        result=asyncio.run(recognize_document_hydraulika(
            files,cat,magazyn=magazyn,chain=steps))
    else:
        result=asyncio.run(recognize_document(
            files,cat,rules_from_db(session),magazyn=magazyn,chain=steps))
    result.used_provider="Multiplekser AUTO (darmowy Gemini, limit Claude)"
    return classify,dzial,result


def select_verify_targets(
    risky: list[tuple[dict, object]],
    page_count: int,
    *,
    max_rows: int = 3,
    max_pages: int = 2,
) -> dict[int, list[str]]:
    """Build a valid bounded Opus request without creating empty page buckets.

    Earlier setdefault(page, []) created a third empty bucket even after
    max_rows was reached, causing bridge validation to reject the entire job.
    """
    chosen: dict[int, list[str]] = {}
    for raw, _position in risky:
        try:
            page = int(raw.get("page_number") or 1)
        except (TypeError, ValueError):
            continue
        name = str(raw.get("nazwa") or "").strip()
        if not 1 <= page <= page_count or not name:
            continue
        if sum(map(len, chosen.values())) >= max_rows:
            break
        if page not in chosen:
            if len(chosen) >= max_pages:
                continue
            chosen[page] = []
        if len(chosen[page]) < max_rows and name not in chosen[page]:
            chosen[page].append(name)
    return {page: names for page, names in chosen.items() if names}
