## Current Phase: 4 — real-textbook re-baseline (autonomous run, user away ~1hr)
## Status: in_progress

**Working autonomously per explicit user instruction: no fabricated data,
ever, in any form — no synthetic textbook content, no hand-tuned fixtures,
no stub satisfying a gate. Everything below runs against real scanned pages
from a real textbook or is explicitly marked as not yet run.**

## Completed
- [x] **Real textbook fixture extracted.** The user said `pk_nag.pdf` was in the repo root; the actual file is `Thermodynamics by PK Nag.pdf` (15.7MB, real scanned P.K. Nag *Engineering Thermodynamics*) — used it as-is rather than blocking on the filename mismatch, noting the discrepancy here per "make the decision, record it, keep moving." No table of contents/outline is embedded in the PDF (`pypdf`'s `.outline` is empty), so chapter boundaries were found by reading the TOC's own text (PDF pages 2-6) and then confirming actual start/end pages by inspecting real page content — the TOC's own printed-page numbers don't map to PDF page indices via a constant offset in this scan (verified: printed page 1 = PDF index 11, but printed page 111 / Chapter 6 actually starts at PDF index 116, not the naively-computed 121 — OCR page-count drift). Chapter 5, "First Law Applied to Flow Processes," confirmed by direct content inspection to span PDF indices 86-115 inclusive (30 pages exactly) — dense with solved numerical examples and end-of-chapter problems, matching the user's own suggested chapter type. Extracted via `scripts/extract_nag_fixture.py` (pypdf, exact page copy, no OCR/text modification) to `tests/fixtures/nag_real.pdf`. Spot-checked through the real `extract_pages()` pipeline: page 1 is the Chapter 5 heading, page 30 is problem 5.18 immediately before the Chapter 6 boundary — confirms the slice is exactly right, not off-by-one.
- [x] Full textbook (`Thermodynamics by PK Nag.pdf`) added to `.gitignore` explicitly (was already covered incidentally by the pre-existing `*.pdf` rule — added a named, commented entry so the intent isn't left to a generic pattern's side effect). `pk_nag.pdf` also added in case the file is later renamed to match the name the user expected.

## Next Immediate Task
(updated as each remaining task below completes)
1. S4 descope: `figure_dependency=essential` -> `is_solvable=false`, excluded from selection; keep `Figure` table + a no-op S4 interface; ADR recorded.
2. Ingest `tests/fixtures/nag_real.pdf` for real (discipline=mechanical), run S2 (regex/heuristic, unchanged — no LLM call exists in S2 yet, see Decisions Made) and S3 (real batched Gemini calls) against it. Report raw candidate/confirmed counts. Explicitly NOT computing precision/recall — no human labels exist for this real content.
3. P5 concept distillation + fingerprinting + clustering against the real detected problems.
4. P6 scoring + selection against the real distilled concepts, applying the user's CoolProp/self-containedness scoring rule.

## Decisions Made
(Phase 1-3 decisions unchanged — see `docs/adr/0001-0006` and prior PROGRESS.md history in git log.)
- Used the real file `Thermodynamics by PK Nag.pdf` in place of the literally-named `pk_nag.pdf` the user described — obviously the same intended book, filename mismatch not worth blocking on.
- Chapter boundaries for the fixture extraction were determined by reading real page content, not by trusting the TOC's stated page numbers arithmetically — this book's OCR/scan has inconsistent printed-page-to-PDF-index offset. Generalize this caution to any future real-book chapter-boundary work: always confirm chapter start/end against actual page content, never compute it purely from TOC page numbers plus an assumed constant offset.
- S2 (`structure.py`) will run **unchanged** against the real content — it's regex/heuristic only, no LLM call exists in it yet (this was a Phase-3-era decision, see `docs/adr/0005`; not revisited in this run). "Run S2 with real Gemini calls" is being read as "run the S2 pipeline stage, whose downstream S3 stage makes real Gemini calls" rather than as an instruction to retrofit an LLM pass into S2 that doesn't exist yet and wasn't otherwise in scope for this run — flagging this reading explicitly rather than silently reinterpreting the instruction.

## Blocked On
Nothing yet for what's been attempted. Will update per-stage below as P5/P6 work proceeds — if a Gemini daily quota is hit, that stage's exact resume state will be recorded here, the run will stop cleanly (non-zero exit), and it will NOT be retried in a loop.

## Known Issues
- (carried forward from Phase 3, still true) S3 never sets `figure_dependency` beyond `NONE`/what S4's descope will now assign — being addressed in this run's Task 2.
- (carried forward) `config/llm_routing.yaml`'s RPM/RPD numbers are still best-effort, unverified against the real AI Studio account page.
- (carried forward) `match_topic_nodes` (S2) still needs real `TopicNode.aliases` to be useful on real chapter titles — untouched in this run.
