# JEV Image Only — E1/E2 shadow validation (2026-10-15)

**Experimental branch**: `feature/jev-only-shadow-e0`.

This is not a production route. Production version remains 1.0.50
(Gemini free-key routing, old matcher/JEV, user login). E1 tests never
upload or approve TXT/RW/PWP, and never edit production DB.

## Pipeline

1. PDF -> 2x high-res page raster via PyMuPDF, no alteration of stored PDF.
2. OpenCV table-grid detection from evidence in each page; conservative
   secondary adaptive threshold; only if needed, constrained Hough-detected
   deskew (0.8–12 degrees). Unknown or contradictory grids fail closed.
3. Candidate row and quantity columns extracted from current grid, never a
   fixed coordinate template. Separate printed names, issued and used quantities.
4. JEV Image 1.14 is the only generative/vision model: family `Choice`, exact
   printed name `Choice`, issued/used quantity `Choice`.
5. Optional **second JEV Image reading** of enhanced-contrast cell. A
   disagreement forces the numeric result to `null`; even agreement is
   still marked for human review.
6. Existing deterministic material matcher can suggest Optima codes without
   changing any alias, stockroom, electrical 1P/3P or other rules.
7. Coverage is **never automatically asserted as complete**, and no code/
   quantity suggestion can be exported or approved from this prototype.

All provider calls go to TypeSafe with
`TypeSafe-Danger-Zone-Images: true`. No Gemini or Claude calls.

## Geometry progress — reproducible frozen evaluation

| Cohort | E0 valid pages | E1 valid pages | Total |
| --- | ---: | ---: | ---: |
| 8 unique older electric PDFs | 6 | 14 | 15 |
| 8 new unique electric PDFs (Oct 15) | — | 15 | 16 |

Cohort SHA-256 prefixes stored privately outside Git at
`/var/tmp/jevonly_shadow_e0/frozen_electric_8.txt` and
`/var/tmp/jevonly_shadow_e0/new_20261015_cohort.txt`.

**Warning:** Valid grid != correct OCR or complete rows. The last page
of the older cohort and first page of one new PDF still fail grid detection
safely. For hydraulics (4-page archived PDF) the grid worked on pages
1 and 2, not on pages 3 and 4.

## New-file live JEV Image-only result

- One frozen new electric document: 2 pages, 90 detected row regions.
- Prior crude ink filter: 64 suspected rows, inflated by stray black grid.
- Line-filtering version: 44 suspected; this is still over-inclusive, *not*
  equal to true handwritten row count.
- Read 20 suspected rows out of 44 in shadow; **24 suspected rows not yet
  analyzed**; full-coverage verification remains incomplete.
- 6.7 s total for the limited 20-row analysis with double quantity reading
  and deterministic matcher suggestions. **Not the time for a full PDF**.
- All 20 printed names got a candidate label from JEV; these labels have not
  been independently audited against the scan.
- 23 amount fields processed in two JEV views: 15 agreements, 8 disagreements.
  Of those, 13 returned a numerical amount with agreement. This is **not
  13/23 accuracy** — no independently verified GOLD is available.
- Matching suggestions generated for 20 names. None approved or exported.
- 13/13 isolated technical tests passed.

## Current limitations/gates for next iteration

1. Improve ink-vs-grid segmentation while proving recall of all handwritten
   rows. A missed row is more dangerous than extra review.
2. Fail open to manual review on missing/unknown layouts, never assume the
   previous page's columns are identical.
3. Detect non-grid handwritten additions and amount overflow, and preserve
   the distinction between issued and used.
4. Assemble independent human-reviewed GOLD for 50–100 amount fields from
   >=10 distinctly authored documents. Compare JEV to Gemini on identical
   bytes and penalize extra/missing rows as strongly as wrong numbers.
5. Only consider production switching after complete, end-to-end, non-regressed
   accuracy has been demonstrated with a safe rollback.

## Reproduction

Use an isolated Docker compose *run*, with this branch's `jev_vision_only`
package and benchmark script mounted read-only, and a private output dir.
Benchmark CLI:

```text
python -m scripts.benchmark_jev_vision_only --geometry-only
  --sha-file /shadow/frozen_electric_8.txt --out /shadow/geometry_frozen.json

python -m scripts.benchmark_jev_vision_only --verify-quantities
  --max-marked 20 --suggest-matches
  --sha-file /shadow/one_new_20261015.txt --out /shadow/new20.json
```

These test invocations use normal provider-rate safeguards, do not save
customer scans in Git, and never open a production background task.
