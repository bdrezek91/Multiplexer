"""Hard safety rules for hydraulic TXT, independent of OCR/matcher/JEV.

Never silently export non-billable ZAS 127, or substitute a generic screw set
for specific RAL/dimension screws. Both OCR and TXT generator enforce this.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(text: str | None) -> str:
    raw=unicodedata.normalize("NFKD",str(text or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"\s+"," ",raw).strip()


def is_ignored_zas127(name: str | None) -> bool:
    n=re.sub(r"[^a-z0-9]+"," ",_norm(name)).strip()
    # Exclude ONLY known non-bookable note, never e.g. FI 127 plumbing items.
    return bool(re.fullmatch(r"(?:zas|zaslepka)\s*127(?:\s*czerwona)?",n))


def _screw_dimensions(name: str) -> tuple[str,str] | None:
    match=re.search(r"\b(\d+(?:[.,]\d+)?)\s*[x×]\s*(\d+(?:[.,]\d+)?)\b",name)
    if match:
        return match.group(1).replace(",","."),match.group(2).replace(",",".")
    return None


def screw_code_safe(source_name: str | None, code: str | None, matched_name: str | None) -> bool:
    source=_norm(source_name)
    if not re.search(r"\bwkret",source):
        return True
    source_dim=_screw_dimensions(source)
    source_color=re.search(r"\bral\s*([0-9]{4})\b",source)
    if not (source_dim or source_color):
        return True
    candidate=_norm(" ".join((code or "",matched_name or "")))
    if not code or not re.search(r"\bwkret",candidate):
        return False
    if "zestaw" in candidate and not (source_dim and _screw_dimensions(candidate)):
        return False
    if source_dim:
        target_dim=_screw_dimensions(candidate)
        if target_dim is None or target_dim != source_dim:
            return False
    if source_color:
        target_color=re.search(r"\bral\s*([0-9]{4})\b",candidate)
        if not target_color or target_color.group(1)!=source_color.group(1):
            return False
    return True
