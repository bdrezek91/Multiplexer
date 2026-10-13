"""Conservative, side-effect-free safety checks for experimental V4 OCR.

Never infer missing quantities from neighbouring columns or silently discard
invalid rows. These flags are diagnostics for GOLD review, not product decisions.
"""
from __future__ import annotations

import math
from typing import Any

from app.modules.ocr.pipeline_hydraulika import _decode_literal_qty


def _safe_amount(value: object) -> float | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        value = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 < value <= 100000 else None


def normalize_raw_quantities(item: dict[str, Any], dzial: str) -> tuple[dict[str, Any], list[str]]:
    """Compare literal marks with numeric interpretation, NEVER guess a conflict."""
    output = item.copy()
    flags: list[str] = []
    for field in ("ilosc_wydana", "ilosc_zuzyta"):
        numeric = _safe_amount(item.get(field))
        raw = item.get(field + "_raw")
        if dzial == "hydraulika" and raw is not None:
            handled, literal = _decode_literal_qty(raw)
            if handled:
                parsed = _safe_amount(literal)
                if parsed != numeric:
                    flags.append(field + ":raw_numeric_conflict")
                    # No silent correction in either direction; force review.
                    output[field] = None
                else:
                    output[field] = numeric
            else:
                flags.append(field + ":unknown_raw_mark")
                output[field] = None
        else:
            if raw is not None and dzial == "elektryka" and str(raw).strip():
                # Numeric entries remain unmodified; discrepant handwritten text
                # is review-only rather than a source of automatic corrections.
                text = str(raw).strip().replace(",", ".")
                raw_number = _safe_amount(text)
                if raw_number != numeric:
                    flags.append(field + ":raw_numeric_conflict")
                    output[field] = None
                else:
                    output[field] = numeric
            else:
                output[field] = numeric
                if raw is None and numeric is not None:
                    flags.append(field + ":missing_literal_evidence")
        if item.get(field) is not None and numeric is None:
            flags.append(field + ":invalid_number")
    if not (isinstance(item.get("nazwa"), str) and len(item["nazwa"].strip()) >= 2):
        flags.append("invalid_name")
    output["_v4_review_flags"] = sorted(set(flags))
    return output, output["_v4_review_flags"]


def evaluate_rows(rows: list[dict], dzial: str, page_count: int) -> tuple[list[dict], list[str]]:
    """Fail closed on bad page IDs or model/schema omissions, retain suspect rows."""
    result = []
    notes: list[str] = []
    if len(rows) > 600:
        raise ValueError("V4 response exceeds maximum rows")
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"V4 item #{i+1} is not an object")
        page = row.get("strona")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= page_count:
            raise ValueError(f"V4 item #{i+1} has invalid page number")
        output, flags = normalize_raw_quantities(row, dzial)
        result.append(output)
        notes.extend(f"row_{i+1}:{flag}" for flag in flags)
    return result, notes
