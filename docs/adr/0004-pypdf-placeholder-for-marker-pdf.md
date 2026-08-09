# 4. `pypdf` as a placeholder extractor; real marker-pdf integration deferred

## Status
Accepted

## Context
TECH STACK fixes PDF-to-markdown extraction as marker-pdf with `--use_llm`,
plus a full-page VLM fallback for math-heavy/scanned pages. marker-pdf is a
large ML-based converter (OCR/layout models via `surya`) — standing it up
needs real model weights and meaningfully more setup/runtime cost than
Phase 2's actual gate requires.

Phase 2's gate is about the *dedup and persistence* logic (S1a/b/c): exact
sha256 match, MinHash-over-shingles cross-edition match, idempotent/resumable
Page persistence. None of that depends on extraction quality — it depends on
getting *some* real per-page text out of a PDF, consistently.

## Decision
`src/practice_forge/ingest/extract.py` uses `pypdf` for per-page text
extraction now, behind the same `extract_pages(path) -> list[PageExtraction]`
signature marker-pdf will eventually implement. Metadata (title/author/
edition) extraction (`ingest/metadata.py`) is a regex heuristic over the
first few pages' text rather than an LLM call, for the same reason: S1
doesn't specify LLM-based metadata extraction, and avoiding an API call here
means dedup can be exercised (and tested) with zero Anthropic cost.

## Consequences
- Works today for genuinely text-based PDFs (not scanned/image-only pages);
  will misdetect math (regex hint patterns, not real parsing) and won't
  handle scanned pages at all — both are marker-pdf's job, not pypdf's.
- Swapping in real marker-pdf later is a one-function change: implement the
  same `extract_pages` signature, no caller changes needed.
- The metadata regex heuristic (`ingest/metadata.py`) expects a loosely
  structured title page (`Title: ...` / `Author: ...` / `Edition: ...`).
  Real textbook title pages are messier (publisher boilerplate, ISBN
  blocks); this will need an LLM pass over the first few pages before it's
  reliable on real books. Tracked as a known gap, not blocking Phase 2's
  gate, which only needs metadata good enough to prove the matching logic.
