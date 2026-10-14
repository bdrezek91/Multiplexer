# Gemini FREE1 / FREE2: real fallback & quota isolation observations, 2026-10-14

**Scope:** test 2 independent configured Google API keys with the currently deployed AUTO V3 router without changing PostgreSQL document items or production settings. Paid Gemini and Claude were NOT called by benchmark commands. Do not print API keys or raw customer OCR outputs.

## User-provided batch inventory

- Nine PDF uploads: 4+2+2+2+2+4+2+2+2 = **22 scanned pages**.
- Four pairs are visually near-identical renditions of the same source (different PDF SHA-256), plus one separate 2-page electrical document: **five distinct visual document sets**.
- Distinct byte-level hashes indicate that the **existing SHA-256-only upload dedup guard would not collapse near-duplicate PDFs** (if uploaded together). This is expected, not a bug in the hash comparison.
- User-provided PDF bytes are available in the ChatGPT conversation sandbox but were **not transferred to the VPS**. Below are real OCR tests on *other, already retained VPS documents* with comparable hydraulic/electrical layouts. Never mislabel these results as direct OCR of the nine uploads.

## Actual Google API behavior

1. A minimal text generation probe verified both FREE1 and FREE2 could return successful Gemini 3.5 Flash-Lite and Gemini 3.6 Flash responses on 2026-10-14. Gemini 3.1 Flash-Lite timed out after 7 sec on both.
2. During the controlled real-document batch, Gemini 3.6 Flash **FREE1 returned HTTP 429 on all five stored-document probes** (once during full OCR; four times at classification), usually within 0.43-0.56s for classification. Do not run more FREE1 requests while exhausted.
3. At the same time Gemini 3.6 Flash **FREE2 returned successful HTTP generation**, proving FREE2 was not blocked by FREE1's currently exhausted quota. This is strong empirical evidence for independent effective capacity, but project IDs were not authenticated or retrieved from Google Cloud. Official rate limits are per Google Cloud *project*, not per API key; separate quotas are certain only if two keys belong to different projects: https://ai.google.dev/gemini-api/docs/rate-limits
4. Real combined router, 2-page hydraulics, 8 stored reference rows: FREE1 classification rejected **308 ms**, FREE2 classification selected **2335 ms**, FREE2 full OCR selected **6683 ms**; entire Gemini+matcher **9.630 sec**, PDF preparation **2.453 sec**; **8/8 exact names** against stored non-GOLD result.
5. Real combined router, 2-page electrics, 25 reference rows: FREE1 rejection **392 ms**, FREE2 classification **2466 ms**, FREE2 full OCR **10678 ms**; Gemini+matcher **14.192 sec**, PDF preparation **2.208 sec**; **24/25 matching names AND amount pairs**, one discrepancy vs stored non-GOLD.
6. Another FREE2 real 2-page hydraulics run returned a response that failed the document schema/row validation: the engine correctly refused to treat it as successful. No DB changes.
7. Dense 3-page hydraulics, 49 stored reference rows, restricted to Gemini 3.6 for both pools: FREE1 rejected and FREE2 responded with **HTTP 503**, so classification failed in **2.776 sec** (PDF prep **2.383 sec**). Full AUTO production retains other free models and Claude fallback; the isolated probe intentionally restricted model to 3.6.

## Deterministic failure injection tests

`backend/tests/test_auto_gemini_free2_fallback.py` exercises `run_ocr_chain` with fake OCR and in-memory Redis:

- HTTP 429 FREE1 -> FREE2 success, independent 10 minute cooldown for FREE1.
- HTTP 503 FREE1 -> FREE2 success, independent 3 minute cooldown.
- Timeout FREE1 -> FREE2 success and 2 minute cooldown, next document skips failed FREE1.
- Explicit separate cooldown keys for FREE1 and FREE2.

**4/4 tests passed** in a no-network Docker container. No Google quota or production Redis was modified by these simulated tests.

## Assessment

- Immediate `429`/`503` errors cause quick fallback (real 308ms / 392ms for `429` before the second attempt). A **true network stall still consumes its per-step timeout** (currently classification 4-5s; full OCR 9-13s) before fallback. The deterministic test timeouts were artificially short and are NOT a production p95 SLA.
- Gemini 3.6 Flash FREE2 can be quick and accurate on simpler docs, but 24/25 on electronics and 503 on dense hydraulics mean quality and 20s including JEV are **not guaranteed**.
- The stronger test of distinct project identities/quotas is Google AI Studio: check the project IDs associated with each API key and verify each project's current RPM/TPM/RPD in Dashboard > Rate limits. Avoid intentionally draining quotas.
- Further user-batch validation requires transferring the nine uploaded originals to a private VPS staging area or submitting them through a read-only test intake; *do not* create production items or auto-post to Optima for benchmarks.
