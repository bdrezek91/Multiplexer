# AUTO V4 Gemini — isolated shadow experiment (13.10.2026)

## Status

V4 is **NOT production enabled**. It is a separate, read-only experimental module; all live documents continue through AUTO V3/Claude/JEV as before. Do not enable export from V4 until an independently verified GOLD dataset proves parity.

## Implementation

- `app/modules/documents/auto_v4.py`: single Gemini request for classification + rows, native JSON output schema, independently checks inferred department against material names (never trusts the model's department alone); sends no product codes or catalog.
- `scripts/benchmark_auto_v4.py`: manual read-only benchmark for one selected document, optionally one page, against stored document items; reports exact name and quantity mismatches. Stored document items are **not independent GOLD**, so a zero mismatch is necessary but not sufficient.
- `scripts/benchmark_auto_v4_parallel.py`: manual, deliberately opt-in multi-page parallel request stress test; not a production route.
- `tests/test_auto_v4.py`: schema, category safety and allowlist tests. Never sends real user data to tests.
- No change to active JEV/matcher logic. No automated Gemini load testing or recurring jobs.

## Results on completed 7dd024c2-1515-4d7b-b6c5-8b2ad74b0cc4

| Experiment | OCR time | Coverage/quality | Status |
|---|---:|---|---|
| Gemini 3.5 Flash-Lite minimal, 3 pages | >25 s | No response | Read timeout |
| Gemini 3.5 Flash-Lite minimal, page 1 | >22 s | No response | Read timeout |
| Gemini 3.6 Flash minimal, page 1 | 6.36 s | 15 rows, 14 matched names, 12/14 identical quantity pairs vs stored baseline | Not GOLD / 2 quantity conflicts |
| Gemini 3.6 Flash minimal, 3 parallel page requests | 6.68 s OCR wall | Only page 1 succeeded, remaining two HTTP 503 (high demand) | Not reliable |
| Gemini 3.6 Flash minimal, full 3 pages | 3.24 s until HTTP 503 | No response | Unavailable |
| Gemini 3.1 Flash-Lite minimal, page 2 | 14.15 s | 19 rows, 18 matched names, 14/18 identical quantity pairs | Not GOLD / 4 conflicts |
| Gemini 3.8 Flash low, page 1 | >25 s | No response | Read timeout |

**No configuration achieved both the 20-second end-to-end limit and equivalent accuracy.** All comparisons are relative to previous production OCR; these are not human-verified truth labels. Some differences may reflect errors in that baseline.

### Test limitations

- APIs may return 429/503 or delay unpredictably. A single fast page is not proof of reliability on all three pages.
- New generic V4 prompt is NOT validated as a replacement for the separately hardened hydraulics and electrics prompts; keep existing safety checks.
- End-to-end time must include queue wait, PDF preparation, complete OCR, matcher, JEV and database finalization; no partial result may be called `done` or exported.
- **Release gate:** >=50 independently checked GOLD samples including challenging handwritten `1` vs `V`, both quantity columns, unusual dimensions, all page counts; 0 silently omitted or fabricated rows, 0 unreviewed material/quantity differences, and meaningful latency distribution (p50/p95). Never claim guaranteed <=20 s on an unbounded external API without a bounded safe failure mode.

## Safe use

Only run this manually, if free Gemini quota permits. Example from `multiplekser/`:

```bash
mkdir -p /var/tmp/multiplekser_v4_shadow
chown 999:999 /var/tmp/multiplekser_v4_shadow
chmod 700 /var/tmp/multiplekser_v4_shadow
# Use the worker image built from the branch containing V4; do not start/recreate production worker.
docker compose -f docker-compose.prod.yml run --rm --no-deps \
  -v /var/tmp/multiplekser_v4_shadow:/shadow \
  worker python -m scripts.benchmark_auto_v4 \
  --document 7dd024c2-1515-4d7b-b6c5-8b2ad74b0cc4 \
  --model gemini-3.6-flash --thinking minimal --timeout 25 --output-dir /shadow
```

Only the authorized VPS owner can inspect the saved raw OCR results (`0600`); test jobs must not alter existing documents or statuses.

## Follow-up V4.1 — strict handwritten amount controls (13.10.2026)

- New `auto_v4_quality.py` reuses production hydraulics `_decode_literal_qty` to inspect the **literal** issue/consumption marks independently of numeric fields. A conflict (`V` vs predicted `1`, dash vs `1`, `1` vs `4`) is NOT silently corrected: set the candidate quantity to `null`, add a row-level review flag. Retain uncertain rows for review.
- Reject invalid source-page numbers; detect malformed row output and preserve diagnostic counts. OCR remains experimental; no V4 item can replace existing item records automatically.
- Unit-of-measure (`jm`) is now a separate schema field, never inferred from the other columns.
- `benchmark_auto_v4.py --page N` now reports `single_page_unscored`, because production rows have no verified source-page mapping. Previous page-vs-whole-document mismatch counts were NOT valid page recall statistics. Parallel benchmarks with failed pages likewise report `incomplete_unscored` rather than misleading 49-row missing counts.
- `gemini-2.5-flash-lite` with `thinkingBudget=0` was checked as an alternative; its API returned **HTTP 404 NOT_FOUND**, explicitly stating it is unavailable to new users. The model is NOT a candidate for the production provider chain on this project's key.
- Isolated tests run with `--noconftest`, `--network none`: **22 passed** after these updates, with no production database or Redis dependency. An earlier no-network run without `--noconftest` failed because the existing repository's autouse fixtures contact Redis at localhost; those errors were environmental, not OCR regressions.
- Release gate unchanged: full-document independently human-verified GOLD, exact names + both quantities + units, correct matcher codes and JEV, with measured end-to-end latency distribution. Experimental code and production AUTO V3 remain isolated.
