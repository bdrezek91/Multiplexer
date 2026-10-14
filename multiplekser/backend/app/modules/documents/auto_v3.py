"""Multiplekser V3 AUTO: classify department from literal OCR labels + header evidence.

Gemini reads the document; only the business matcher/JEV chooses product codes.
Never choose a warehouse catalog on contradictory or absent evidence.
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
        return header,96.0 if votes[header]>=2 else 82.0,"nagłówek + słownik"

    winner=max(votes,key=votes.get)
    loser="hydraulika" if winner=="elektryka" else "elektryka"
    if votes[winner]>=3 and votes[winner]>=votes[loser]*3:
        return winner,77.0,"słownik nazw materiałów"
    raise AmbiguousDepartment(
        "Nie udało się jednoznacznie ustalić działu. Sprawdź formularz przed ponowną próbą."
    )


def recognize_gemini_primary(
    files, session, magazyn, *, model=None, event_callback=None, cooldown_store=None,
):
    """Gemini AUTO: a bounded sequential chain of FREE models.

    Start with the fastest free Gemini. Try other free models only on timeout,
    API 429/503, bad schema or low-confidence department classification.
    Shared Redis cooldown avoids retrying a blocked model on the next document.
    If all free Gemini models fail, the document fails safely. JEV still chooses codes.
    """
    import asyncio
    import time

    from app.core.config import settings
    from app.modules.ocr.classify import classify_document
    from app.modules.ocr.chain import OCRChainStep
    from app.modules.ocr.image import classification_header_preview
    from app.modules.ocr.pipeline_elektryka import recognize_document
    from app.modules.ocr.pipeline_hydraulika import recognize_document_hydraulika
    from app.modules.ocr.providers import GeminiProvider
    from app.modules.matcher import rules_from_db
    from app.modules.products import Catalog

    started_total = time.perf_counter()
    keys = (("FREE1", settings.gemini_api_key_free),
            ("FREE2", settings.gemini_api_key_free_2))
    keys = [(pool, value) for pool, value in keys if value]
    if not keys:
        raise RuntimeError("Gemini: darmowy klucz nie jest skonfigurowany")
    if model is not None and model not in {"gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"}:
        raise ValueError("Niedozwolony model Gemini AUTO")
    provider = GeminiProvider()
    # Production probe (14.10.2026): 3.5 Lite & 3.6 responded quickly on
    # both projects; 3.1 Lite timed out on both even for trivial text.
    # Preserve 3.1 as LAST fallback, not the second slow attempt.
    candidates = [
        ('gemini-3.5-flash-lite', 4, 13),
        ('gemini-3.6-flash', 5, 12),
        ('gemini-3.1-flash-lite', 4, 9),
    ]
    if model is not None:
        candidates = [row for row in candidates if row[0] == model]
    # Different step labels give each Google project independent Redis
    # cooldown and diagnostics. Keep FREE1 labels for historical cooldowns.
    def make_steps(use_classification: bool):
        steps = []
        for name, classify_timeout, full_timeout in candidates:
            for pool, api_key in keys:
                label = (f'AUTO Gemini {name} darmowy' if pool == 'FREE1'
                         else f'AUTO Gemini {name} darmowy FREE2')
                steps.append(OCRChainStep(
                    label, provider, name, api_key,
                    classify_timeout if use_classification else full_timeout,
                ))
        return steps

    classify_chain = make_steps(True)
    full_chain = make_steps(False)
    start=time.perf_counter()
    # Hard cap includes serial model retries on both projects.
    classification=asyncio.run(asyncio.wait_for(classify_document(
        [(classification_header_preview(files[0][0]), "image/jpeg")],
        chain=classify_chain, event_callback=event_callback,
        cooldown_store=cooldown_store, min_confidence=65,
    ),timeout=15))
    classify_seconds=round(time.perf_counter()-start,3)
    if classification.fallback or classification.confidence<65:
        raise AmbiguousDepartment(
            "Gemini FREE: niejednoznaczny dział — wymagana ponowna próba"
        )
    dzial=classification.dzial
    # A successful short classification is not proof that the same model will
    # finish a dense handwritten OCR. Real 2-page shadow: Gemini 3.6 FREE2
    # completed 8/8 names in 4.45s, whereas 3.5 Lite had long full-OCR
    # timeouts. Prefer 3.6 for the FULL document, first on the pool that
    # classified successfully, then the other project.
    prefer_free2 = classification.used_provider.endswith('FREE2')
    # Quality-safe adaptation: NEVER reorder model families (3.6, 3.5 Lite,
    # 3.1 Lite). Only choose which FREE project goes first WITHIN each model.
    # Historical priority is preserved unless BOTH projects have >=3 validated
    # full-OCR timings and one is measurably faster by at least 1 second.
    lookup = getattr(cooldown_store, "validated_latency_ms", None)
    latency = {}
    if callable(lookup):
        for step in full_chain:
            latency[step.label] = lookup(step.label, f"full_ocr_{dzial}")

    # Freeze model groups before list.sort: CPython temporarily exposes an
    # empty list while calculating sort keys.
    by_model = {name: [candidate for candidate in full_chain if candidate.model == name]
                for name in ("gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite")}

    def sort_free_pair(step):
        model_rank = {"gemini-3.6-flash": 0, "gemini-3.5-flash-lite": 1,
                      "gemini-3.1-flash-lite": 2}[step.model]
        same = by_model[step.model]
        both = len(same) == 2 and all(latency.get(candidate.label) is not None for candidate in same)
        measured = [latency[candidate.label] for candidate in same] if both else []
        if both and max(measured) - min(measured) >= 1000:
            return model_rank, latency[step.label]
        return model_rank, step.label.endswith('FREE2') != prefer_free2

    full_chain.sort(key=sort_free_pair)
    remaining = 26 - (time.perf_counter() - started_total)
    if remaining <= 0:
        raise TimeoutError('Budżet Gemini AUTO wyczerpany')
    start=time.perf_counter()
    catalog=Catalog.from_db(session,dzial=dzial)
    if dzial=="hydraulika":
        result=asyncio.run(asyncio.wait_for(recognize_document_hydraulika(
            files,catalog,magazyn=magazyn,chain=full_chain,
            event_callback=event_callback, cooldown_store=cooldown_store,
        ),timeout=remaining))
    else:
        result=asyncio.run(asyncio.wait_for(recognize_document(
            files,catalog,rules_from_db(session),magazyn=magazyn,chain=full_chain,
            event_callback=event_callback, cooldown_store=cooldown_store,
        ),timeout=remaining))
    ocr_seconds=round(time.perf_counter()-start,3)
    if not result.pozycje:
        raise ValueError("Gemini FREE: brak poprawnych pozycji — wymagana ponowna próba")
    # Stored only on the in-memory result for this task; catalog data and
    # matching rules remain untouched and are not shared across requests.
    result._matching_catalog_for_jev = catalog
    return classification,dzial,result,{
        "timing_classification":int(classify_seconds*1000),
        "timing_ocr_matcher":int(ocr_seconds*1000),
    }
