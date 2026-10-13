# AUTO V4 local CPU/GPU OCR and upload-integrity benchmarks (2026-10-13)

## Scope and production safety

V4 is still **shadow-only**. It does not modify document items or JEV. Tests use the user's authorized Windows PC reached through private SSH tunnels from the VPS; no publicly exposed OCR port is necessary.

## Tested components

- Private local OCR: RapidOCR / ONNX Runtime DirectML on RTX 4070 SUPER (separate Python virtual environment; does not replace the PłytyOS CPU OCR worker).
- Existing CPU RapidOCR tunnel over SSH.
- Qwen3-VL 4B Ollama on the same RTX, in a limited experimental role for handwritten quantities only.
- `auto_v4_geometry.py`: read-only blue ink pixel counts in individually identified form rows; no quantity prediction.
- `auto_v4_electric.py`: separate experimental electrical OCR path using high-confidence numeric OCR text boxes, calibrated against the first-page quantity header, with continuation-page column centers. Low confidence or duplicate numeric boxes produce review flags; unassigned boxes are never silently dropped.
- `_prepare_distinct_sources` in `ocr_processing.py`: exact SHA-256 detection of accidentally repeated multipart uploads. Dedup only identical *whole source files*, never repeat material names across genuinely different pages.

## Measurements (single-document measurements; NOT full GOLD)

| Test | Result |
| --- | --- |
| Hydraulics, three pages, CPU RapidOCR | 13.05 seconds, 376 OCR text lines total |
| Same three pages, DirectML after warm-up | approx. 1.96 seconds, 376 OCR text lines total |
| DirectML vs CPU text | SHA-256 of normalized OCR text list identical for each of 3 pages. Numerical OCR confidence scores differ; handwritten quantity truth NOT established |
| Hydraulic blue-ink detector, file A | threshold 110: 47/49 production labels found, 4 additional candidates; two omissions are handwritten INNE annotations |
| Hydraulic blue-ink detector, file B | threshold 140: 8/8 production labels found, no extras |
| Qwen3-VL local handwriting-only, 3 separate cropped-page requests | 10.86 s aggregate OCR; 40/45 exact pairs vs stored non-GOLD baseline (5 disagreements) |
| Qwen3-VL, all 3 crops in one request | truncated output / invalid JSON at output budget 1400: NOT viable |
| Gemini 3.6 cropped cells | HTTP 429 (quota exhaustion) |
| Gemini 3.1 cropped cells | read timeout after 14 s |
| Electric sample, numeric OCR geometry | 20 distinct nonempty candidate rows, all 20 match the de-duplicated stored label and quantity pairs (1 remaining manual row not in candidate list). Source DB mistakenly had 42 rows because the same 2-page PDF was uploaded twice |

**Do not use the label coverage as true recall or the matching quantity count as GOLD accuracy.** A validated handwritten corpus, an explicit review of printed vs handwritten material lines and different form versions, and end-to-end JEV timing are release gates.

## Crucial upload duplicate discovery and fix

A production document listed 42 stored items, with 21 identical entries duplicated in the same order. The two uploaded PDFs are byte-for-byte identical with the same SHA-256 hash. Multi-file OCR processed two identical 2-page PDFs as four pages, duplicating all 21 real item rows. A read-only benchmark proved the new SHA-256 source dedup returns two **byte-identical** prepared page JPEGs matching the first source; 1 of 2 uploaded PDFs is skipped. Existing completed document output has intentionally NOT been changed or automatically deleted.

The integrity guard is independent of V4 and is suitable as a production fix when its tests pass. A future upload API enhancement could alert the user at upload time; current guard records a `duplicate_upload` history event and avoids duplication before OCR.

## Next release gate

- Independently reviewed GOLD material sheets, including true blanks, crossed-out digits, checkmarks, handwritten INNE, both quantity columns, and multiple electrical form layouts.
- Explicit zero unexpected quantity changes, zero silent omissions, clear review flags for differences.
- Reproducible p50/p95 elapsed from document acceptance to finished item list and JEV.
- No unbounded GPU dependency: if PC is offline, fall back safely to the existing V3 chain. Private tunnels must not become public OCR endpoints.
