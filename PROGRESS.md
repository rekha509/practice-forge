## Current Phase: 10 — S10 rendering gaps fixed for real; blocked on a real, external time-gate (quota reset) for the rest
## Status: solutions manual now embeds real Python listings + real typeset math (was literal escaped LaTeX/missing code — both fixed and tested). Blocked on gemini-flash-latest's real daily quota resetting (UTC) before independent re-verification, ledger-commit, and the no-repeat proof can run. See bottom-most section for the exact resume point.

**Everything in this run is real.** No synthetic textbook content, no
hand-tuned fixtures, no stub satisfying a gate. Every number below comes
from a real `pf` CLI command against real ingested content from
`tests/fixtures/nag_real.pdf` (P.K. Nag *Engineering Thermodynamics*,
Chapter 5, "First Law Applied to Flow Processes") or a real Gemini API
call. Where something doesn't work well on real content, or a target
can't be met at this scale, it's reported as found — not patched to look
better, not silently downgraded.

## Completed (this autonomous run, chronological)

1. **Real fixture**: `tests/fixtures/nag_real.pdf` — 30 real scanned pages (PDF indices 86-115) extracted from the real textbook (`Thermodynamics by PK Nag.pdf`, gitignored, never committed). Chapter boundaries found by reading actual page content, not trusting the TOC's stated page numbers (this scan's printed-page-to-PDF-index offset isn't constant).
2. **S4 descoped** to detect-and-exclude only (`docs/adr/0007`) — no vision interpretation. Conservative text-only classifier (`figures/figures.py`): any figure/diagram reference in a problem's own text → `ESSENTIAL` → `is_solvable=False`. Confirmed empirically that `Page.has_figure` is useless on a scanned book (every page is one raster image, so it's `True` unconditionally) — the classifier doesn't use it.
3. **Real S1 ingest**: `pf ingest tests/fixtures/nag_real.pdf --discipline mechanical` → book `f5b5bf5f-e6f7-4c8b-9d4e-7bfdc581ceb2`, 30 pages. Title extraction fell back to "Unknown Title" (real book's title page doesn't match the `Title:`-literal heuristic — predicted in `docs/adr/0004`, now confirmed on real content).
4. **Real S2**: one "Untitled" section spanning all 30 pages — the `Chapter N` regex doesn't match this book's real OCR'd headings. Reported as a real, unfixed gap (see Known Issues), not patched to fit this one book.
5. **Real S3, after fixing a real bug found on real content**: original `detect_candidates` checked only each page's first line, which found **zero** candidates (real headings appear mid-page after OCR'd running headers; a page can hold two examples). Rewrote to scan every line with cross-page span support — a genuine generalization fix, verified not to regress the existing synthetic-fixture tests. Result: **8 candidates, all 8 confirmed as genuine worked examples** by a real batched Gemini call (`gemini-flash-lite-latest`; 5707 in / 1626 out tokens, $0). Spot-checked extracted `given`/`find`/`final_answer` against real textbook values — correct. **Precision/recall deliberately NOT computed** — no human has labelled this content.
6. **Real S4 applied**: of the 8 confirmed problems, **5 → `figure_dependency=none`, 3 → `essential` and excluded**.
7. **Found and fixed a real infrastructure bug**: `tests/conftest.py`'s `db_session` fixture truncated the *same* database `pf ingest` writes to — running `pytest` mid-session silently deleted the real ingested book. Root-caused immediately, fixed properly: created a separate real `practice_forge_test` Postgres database, added `TEST_DATABASE_URL` + `db/base.py::make_session_factory()`, repointed `conftest.py`, migrated it. Verified: the real book now survives full test-suite runs.
8. **Real S5 (concept distillation)**, after fixing a second real bug (prompt templates used `.format()` but contain literal LaTeX braces like `\frac{a}{b}`, which `.format()` misparsed as placeholders — failed live, fixed by switching to `.replace()` in both S3 and S5's prompt assembly): real batched Gemini call distilled governing equations/assumptions/method from the 5 solvable problems. SymPy `parse_latex` + `srepr` canonicalization (needed `antlr4-python3-runtime==4.11`, added as a real dependency) — 1 of the resulting LaTeX equations failed to parse and was gracefully handled (logged, fallback fingerprint component), not hidden. Embeddings via `gemini-embedding-001` (not BGE-M3 — `docs/adr/0008`; real API call, verified 3072-dim, migration `0002` widens the pgvector columns to match). Result: **5 concept cards, 5 distinct clusters** (no duplicates among 5 genuinely different physical scenarios — verified non-degenerate via unit-norm embeddings and distinct fingerprints).
9. **Real S6 (scoring)**: real batched Gemini call scored all 5 concepts on the six spec'd axes; `eligible_extension_types` computed deterministically in code (never LLM-invented) from each concept's gating fields × the mechanical profile's allowed extension types. Prompt explicitly instructs the scorer not to penalize `self_containedness` for steam/gas-table lookups CoolProp can supply directly, per the user's scoring note. `physics_informed` intentionally never auto-gated (needs real judgment, not a boolean rule). **5/5 scored.**
10. **Real S7 (selection)**: real constraint-checking algorithm (no LLM) run against the real scored pool. **Result: pool_size=5, cannot reach the 20-problem target — reported honestly, not padded.** 2/8 hard constraints pass (≤2 physics_informed: 0; max pairwise cosine 0.787 < 0.85 threshold); 6/8 fail with concrete real numbers (0 distinct topics — direct consequence of S2's flat-section gap; difficulty mix 1 easy/2 medium/2 hard vs. the 6/9/5 target; etc).

Full non-LLM test suite: 26/26 passed throughout (re-verified after every code change), against the now-isolated test database. `ruff check` and `mypy --strict` both clean throughout. Six commits, one per task, all pushed to `master` locally (not pushed to any remote).

## The headline finding
**Concept-cluster survival after figure-dependent exclusion: 5, not ≥60.**
Flagged per the user's explicit instruction. This is not a defect in P5's
logic — it's the correct, honest consequence of ingesting one 30-page
chapter excerpt instead of a full textbook. The 20-per-set / ≥60-across-
three-runs targets in the original spec assume whole-book ingestion.
Re-run this pipeline against the full `Thermodynamics by PK Nag.pdf` (all
~700 pages) rather than the 30-page excerpt to get a real read on whether
the targets are reachable at actual book scale. This session deliberately
used a small excerpt to keep the real-Gemini-call budget and autonomous
run time bounded — not because the pipeline can't handle more.

## Decisions Made (this run, in addition to `docs/adr/0001-0008`)
- Used the real file `Thermodynamics by PK Nag.pdf` in place of the literally-named `pk_nag.pdf` the user described — same book, obviously.
- Chapter boundaries confirmed by reading real page content, never by trusting TOC page numbers arithmetically (this book's scan has inconsistent OCR pagination offset).
- `detect_candidates` rewritten to scan every line, not each page's first line, with cross-page span support — real generalization fix, not fixture-tuning.
- `MAX_CANDIDATE_CHARS=4000` caps a real degenerate case (this book's end-of-chapter exercises are an unlabelled numbered list, not individually "Problem N.M"-prefixed, so the span-to-next-heading logic swallowed 14000+ characters) — a safety net, not a fix for the underlying under-segmentation (recorded below).
- Test suite repointed at a dedicated `practice_forge_test` database, permanently, after real data loss during this run.
- Prompt template assembly switched from `.format()` to `.replace()` everywhere it existed, after a real failure on real LaTeX-containing content.
- `gemini-embedding-001` used instead of BGE-M3 (`docs/adr/0008`) — real API already available under the active provider pivot, avoids standing up local model infrastructure under this run's time budget.
- `eligible_extension_types` computed deterministically in code, never asked of the LLM — mechanical function of already-known fields, and asking an LLM to reproduce deterministic logic just adds a failure mode for no benefit.
- S7's real selection algorithm reports `can_reach_target=False` plainly rather than returning a padded/relaxed-beyond-recognition set when the pool is genuinely too small — matches the user's explicit "a blocked phase honestly recorded is a good outcome" instruction.

## Blocked On
Nothing. Gemini daily quota was not exhausted at any point in this run
(single digits to low tens of requests against `gemini-flash-lite-latest`,
out of 1000/day; a handful against `gemini-flash-latest` for S5/S6, out of
~250/day — comfortable headroom remained). No `DailyQuotaExhausted` was
ever raised.

## Known Issues (real, found this run, not yet fixed)
- **S2's chapter-heading detection does not work on real OCR'd content at all.** One "Untitled" section for the whole 30-page excerpt. This directly caused S7's "0 distinct topics" constraint failure — fixing S2 (smarter heading heuristic, or the LLM-based TOC pass the original spec called for and Phase 3 deferred) would very likely change several downstream numbers. Highest-leverage fix to make next, given how many other stages' honest failures trace back to it.
- **This book's end-of-chapter numbered exercises (5.1, 5.2, ... under one "PROBLEMS" header) are invisible to S3.** Only "Example N.M" worked examples are detected; the exercise list needs a numbered-list-under-known-header pattern that doesn't exist yet.
- **S3/S4/S5/S6's real accuracy on this book's content is completely unvalidated against human judgment.** All are real pipeline output, not verified-correct output. Do not cite "8 confirmed," "5 concepts," or any score as ground truth without a human checking it.
- **`ingest/metadata.py` doesn't extract title/author from this real book** (falls back to "Unknown Title") — predicted in `docs/adr/0004`, now confirmed.
- **`gemini-embedding-001` calls are not yet covered by `config/llm_routing.yaml`'s rate limiter** — only `generate_content`-style calls are modeled there. Not hit in this run (5 embeddings is trivial volume) but a real gap before running at book scale.
- **S7's full MMR + constraint-relaxation-in-declared-order logic is implemented but never exercised** — the real pool (5) never reached the ≥20 threshold where that code path activates. Untested against anything but the trivial "pool too small" path.
- (carried forward, unchanged) `config/llm_routing.yaml`'s RPM/RPD numbers are still best-effort, unverified against the real AI Studio account page.
- (carried forward, unchanged) `match_topic_nodes` (S2) needs real `TopicNode.aliases` — moot right now since S2 isn't detecting real chapters on this book at all.

## Completed (S2 TOC rebuild + quota/batching session, 2026-08-09)

1. **S2 rewritten to be TOC-driven** (`structure/toc.py`, new), per the original spec's design — regex (`detect_sections`) is now the fallback, not primary. One real LLM call (`stage="s2_structure"`) parses the book's own table of contents into a chapter list; real `difflib` fuzzy matching locates each chapter's true starting page in the ingested content. Built and validated against a new real 80-page fixture (`tests/fixtures/nag_s2_validation.pdf`, chapters 3-6 of the real book) — deliberately separate from `tests/fixtures/nag_real.pdf`, which is reserved for the user's own hand-count and was never touched.
2. **Two real matching bugs found and fixed via live validation**, not assumed:
   - First implementation matched each page's first 3 lines against the TOC title. On a chapter's *true* start page the title is immediately followed by body prose, which diluted the fuzzy-match ratio below a later page's shorter, noisier running header — wrong page won, and one chapter (6) fell just under the 0.55 threshold entirely (measured: 0.23 for the true page vs. 0.60 for a wrong one; Chapter 6 measured 0.528, just under threshold). Result before fix: `chapters_located=3` of 4 locatable, with wrong page boundaries.
   - Narrowing to first-line-only fixed that, but broke titles that print wrapped across two lines (confirmed: "Second Law of" / "Thermodynamics" on separate lines) — the truncated line let a same-family chapter title false-match at a higher score (0.836) than the true, truncated match (0.634).
   - Final fix: for each page, try matching against its first 1, 2, and 3 non-blank lines and keep that page's best score. Verified live: **4/4 locatable chapters recovered, in correct order, with page boundaries matching hand-computed ground truth exactly** (Ch3→page 6, Ch4→page 31, Ch5→page 49, Ch6→page 79).
3. **Found and fixed a real scalability bug in S5 and S6**: both sent every one of a book's items in a single unbatched LLM call (unlike S3's chunked `BATCH_SIZE=20`). At the full-book projected scale (~117 solvable concepts) this would exceed `max_tokens` and fail. Chunked both the same way S3 already does (`BATCH_SIZE=10` for S5, `15` for S6 — smaller than S3's 20 since each item's schema carries more free-text fields).
4. **Found and fixed a real bug in the embedding call, confirmed live**: `gemini-embedding-001`'s batch endpoint hard-rejects over 100 items per request (`400 INVALID_ARGUMENT`, verified with a live 150-item call). `embed_texts` sent all of a book's texts in one call — fine at 30-page scale (5 items), would crash at the full-book projected scale (~117). Chunked at the confirmed limit.
5. **Found and fixed a real observability gap**: the CLI never called `logging.basicConfig()`, so `llm/client.py`'s per-request structured usage log (job_id/stage/tokens/cost) was silently dropped at INFO level all session — most of this session's real per-stage token counts were never durably captured. Fixed: `practice_forge.llm` logger now writes to both stderr and an appended JSONL file (`data/llm_usage.log`), so a real multi-day, multi-invocation ingest can be aggregated afterward.

## Real Gemini usage — 30-page run, and 700-page projection

**What is precisely known:** one real S3 confirm call = 5707 input / 1626 output tokens (captured via a manual debug script before the logging fix existed). Every other stage's exact historical token count from the original 30-page run was lost to the logging gap above and cannot be honestly reconstructed after the fact — re-running the real pipeline against the *same* book to recapture it risks inserting duplicate rows (none of S3/S5/S6 check for existing output before inserting), so it was not attempted. Going forward, `data/llm_usage.log` captures this for real, per-request, for every run from now on.

**What is known precisely from real, already-persisted counts** (not re-run, just queried): the 30-page book has 1 section, 8 confirmed `SourceProblem`s, 5 solvable, 5 `ConceptCard`s, 5 `ConceptCluster`s, 5 `CandidateScore`s — all in a single batch per stage (well under each stage's `BATCH_SIZE`).

**700-page projection** (23.3x page-count scale-up from the 30-page real counts, assuming roughly uniform problem density across chapters — a real, disclosed assumption, not verified across the whole book):
- Confirmed problems: ~187 (8 × 23.3); solvable after S4: ~117 (matches this session's earlier ~117 estimate)
- **S2** (structure): 1 request, fixed — TOC parsing doesn't scale with page count
- **S3** (detect): candidates ≥ confirmed count; at `BATCH_SIZE=20`, ~10-18 requests
- **S5** (distill): ~117 concepts at `BATCH_SIZE=10` → ~12 requests
- **S6** (score): ~117 cards at `BATCH_SIZE=15` → ~8 requests
- **S4**: 0 requests (no LLM call)
- **Total: ~31-39 real Gemini requests for a full 700-page ingest.**

Against the free-tier daily caps in `config/llm_routing.yaml` (`gemini-flash-lite-latest`: 1000 RPD / 15 RPM; `gemini-flash-latest`: 250 RPD / 10 RPM) this is comfortable headroom — **quota exhaustion within a single day is not expected**, contradicting the premise that would require multi-day checkpointing. This is a request-*count* projection with real structural grounding (actual batch sizes × real candidate/concept counts); it is not a token-*volume* projection — only one real per-request token sample exists (S3's), not enough to project total token cost with confidence, and `config/llm_routing.yaml`'s RPM/RPD are still the empirically-probed-but-unverified-against-the-account-page numbers from `docs/adr/0006`.

**Not yet addressed**: `gemini-embedding-001` calls still aren't covered by the rate limiter (`config/llm_routing.yaml` only models `generate_content`-style calls) — a real gap, not hit yet because embedding volume is trivial relative to any plausible free-tier cap, but unverified.

## Known Issues (updated)
- (all Known Issues from the prior run carried forward except the S2 heading-detection gap, now fixed — see above)
- S2's chapter-heading detection is fixed for the TOC-driven path; the plain regex fallback (`detect_sections`) is unchanged and still won't match this book's real OCR'd headings on its own — only relevant if a book has no locatable TOC.
- Given the 700-page request-count projection shows comfortable headroom against daily caps, **Task #24 (multi-day resume checkpointing) may not be necessary as originally scoped** — flagging this rather than building unneeded infrastructure or silently skipping the user's instruction. Pipeline stages S2-S7 still have no partial-resume today (only S1 ingest does, page-level) — a crash mid-run would require re-running that stage from scratch, which is a real resilience gap independent of quota.

## Completed (idempotency + embedding rate limiting session, 2026-08-10)

User decision on the open question above: Task #24 (multi-day checkpointing) is
skipped — the quota projection holds. Instead, made S3/S5/S6 idempotent, which
gives crash-resume for free AND fixes a real correctness bug idempotency alone
would have papered over. Docker Desktop crashed/hung twice mid-session
(`npipe` connection errors, stray duplicate processes) — recovered both times by
killing stray `Docker Desktop`/`com.docker.backend` processes and relaunching;
no data was lost (Postgres's own transactional DDL rolled back cleanly once,
see below), but flagging the instability in case it recurs.

1. **Migration 0003** (`migrations/versions/0003_card_source_problem_id.py`) adds `concept_cards.source_problem_id` — **NOT NULL + UNIQUE**, enforced by the database, not just application code. First attempt used the full descriptive revision id (`0003_concept_card_source_problem_id`, 36 chars) — failed writing `alembic_version` (that column is `varchar(32)`), but Postgres's transactional DDL rolled the whole migration back cleanly, so no partial schema/data damage resulted. Renamed to `0003_card_source_problem_id` (27 chars) and re-ran clean. The 5 pre-existing dev `concept_cards` rows (and their dependent `concept_clusters`/`candidate_scores`) predated this column and had no way to backfill it — deleted in the migration per explicit instruction. Applied to both the real dev DB and `practice_forge_test`; verified all three tables at 0 rows post-migration.
2. **S3 idempotent**: `run_detection` now skips any candidate already persisted, keyed on **(book_id, page_no, statement_md)** — deliberately NOT bare (book_id, page_no) as originally suggested. Checked real data first: book `f5b5bf5f...`'s page 23 genuinely has two distinct worked examples. A page_no-only key would treat the second real problem on that page as a duplicate of the first and silently drop it on every re-run — the exact silent-breakage failure mode idempotency exists to prevent, just inverted. `detect_candidates`/`ConfirmBatchItem`/`default_llm_confirm_batch`/the S3 prompt remain completely untouched, per the standing freeze — only the persistence-layer guard in `run_detection` changed.
3. **S5 idempotent**: `run_concept_distillation` filters out problems that already have a card (via the new `source_problem_id`) before batching, so a re-run doesn't re-spend LLM quota either. **Found and fixed a second real bug in the same pass**: `_cluster_cards` only ever matched a new card against other cards from the SAME call, never against clusters already persisted from an earlier run. Combined with idempotency's filtering, a genuine duplicate concept introduced in a later/resumed run would land in its own new cluster instead of merging — silently defeating the no-repeat guarantee across resumed runs, and across every book in a discipline (clusters are discipline-scoped by design). Fixed: every call now loads the discipline's existing clusters first and matches new cards against those too.
4. **S6 idempotent**: `run_scoring` skips any `ConceptCard` that already has a `CandidateScore`, keyed on `concept_card_id` (already UNIQUE on that table). Also made `run_scoring` accept an injectable `llm_client`, mirroring S5, so it's testable without a real API call.
5. **New tests, all using fake LLM clients (no real API calls, no accuracy claim)**: `tests/test_concepts.py` (idempotent re-run; a genuine cross-run cluster-merge test that specifically exercises the `_cluster_cards` fix), `tests/test_scoring.py` (idempotent re-run), `tests/test_detection.py::test_detection_idempotent_and_preserves_same_page_multi_problem` (idempotent re-run AND the same-page-two-problems safety property, hand-built rather than relying on incidental fixture content). `tests/conftest.py`'s `db_session` fixture now also truncates `concept_cards`/`concept_clusters`/`candidate_scores` — `concept_clusters` is discipline-scoped, so a stale row from a prior test could otherwise cause a false cross-test cluster merge via the fix above.
6. **Embedding rate limiter gap closed**: `embed_texts` now acquires from a `RateLimiter` before each chunked call, the same mechanism `LLMClient.complete` uses — confirmed a fresh `RateLimiter()` instance safely shares persistent daily-count state (read/written to the same JSON file on every call, never held in memory). No real RPM/RPD number for `gemini-embedding-001` exists anywhere (ADRs 0006/0008 both flag it unaddressed) — added a deliberately conservative placeholder (`rpm: 5, rpd: 100`) to `config/llm_routing.yaml`, clearly marked unverified. The 700-page projection needs ~2 embedding calls total, so this is far from binding either way.

Full non-LLM suite: 35/35 passed (up from 31 — 4 new idempotency tests). `ruff check` and `mypy --strict` both clean throughout.

## Completed: full ~781-page book run through S1-S7 (2026-08-10)

**Book**: `Thermodynamics by PK Nag.pdf`, all 781 real pages (not the 30-page excerpt). `book_id=4d97664c-50ee-4c77-83b8-7951efae4d60`. Real Gemini calls throughout, no stubs, no synthetic content.

**Two real bugs found and fixed at this scale, neither visible at 30/80 pages:**
1. **NUL bytes crashed S3's persistence.** `run_detection`'s single end-of-run flush failed with "PostgreSQL text fields cannot contain NUL bytes" after 6 real confirm batches had already succeeded — rolling back and discarding all 84 already-confirmed, already-quota-paid-for problems. Checked the persisted page markdown directly rather than assuming: **none** of the 781 real pages contain a NUL byte, so the source was an LLM-generated field (`given`/`find`/`final_answer`), not OCR text. Fixed with a shared sanitizer (`llm/sanitize.py`) applied to every free-text field S3/S5/S6 persist from LLM output, `run_detection` now commits per batch (not once at the end, so one bad row can't erase earlier good batches), and `ingest/extract.py` strips NUL at the source too (defense in depth for OCR text specifically, even though it wasn't this crash's actual cause). Re-ran detection clean.
2. **MAX_TOKENS truncation silently zeroed two whole S5 batches.** `gemini-flash-latest`'s thinking tokens draw from the same budget as visible JSON output; 2 of 6 distillation batches landed `output_tokens + extra_tokens` right at `max_tokens=8192`, truncating the array mid-response. `call_batch` already handles a truncated/unparseable array safely (returns all-`None`), but that meant the whole batch's items produced zero cards, not a partial loss — confirmed exactly: 51 solvable problems in, only 31 distilled, and 51 − 31 = 20 = the two failed batches' combined size. Fixed by raising S5's `max_tokens` to 16384, and added a generic warning in `call_batch` (shared by S3/S5/S6) whenever `stop_reason == "MAX_TOKENS"` so this is visible in the moment for every stage, not just reconstructible after the fact. Idempotency paid off immediately here: re-running `pf distill` only reprocessed the 20 missing problems, not all 51.

**Real S2 (TOC-driven) result**: `toc_entries_parsed=22, chapters_located=22` — **all 22 real chapters located, in correct order**, matching the book's actual structure end to end (Front Matter, Introduction, Temperature, ... through Transport Processes in Gases). Full validation of the TOC-driven rewrite at real scale, not just the 80-page validation fixture.

**Real S3 result**: 66 confirmed problems (59 worked examples, 7 exercises) from real batched Gemini confirm calls. Two things worth disclosing plainly, not glossing over:
- This is well below the ~187 projected from the 30-page excerpt's rate — confirms the user's own flagged concern that the 30-page excerpt (worked-examples-dense, zero end-of-chapter exercises) was not representative of the whole book's real density.
- **The S3 confirm step shows real run-to-run variability**: the crashed first attempt had already confirmed 84 problems before the NUL-byte flush failure (lost entirely to rollback); the clean re-run against the identical candidate set confirmed only 66. Candidate detection itself (`detect_candidates`) is deterministic regex over unchanged page text, so this ~22% swing is the LLM confirm call's own sampling variance, not a candidate-detection difference. Recorded here rather than silently treating either number as "the" real count — this is exactly the kind of measured-as-is behavior the user asked for, and it means any single run's confirmed-problem count should be read as one real sample of a noisy process, not a fixed ground truth. Also notable: "Work and Heat Transfer" (pages 44-68) shows 0 confirmed problems in this run despite known real worked examples there (seen directly in earlier page-content inspection this session) — most likely the same confirm-variance, not a structural gap, but not independently verified.

**Real problems-per-chapter distribution** (post-S4; `solvable` is what S5 actually distills from):

| Chapter | Pages | Total | Solvable | Excluded (figure-essential) |
|---|---|---|---|---|
| Front Matter | 1-11 | 0 | 0 | 0 |
| Introduction | 12-30 | 1 | 1 | 0 |
| Temperature | 31-43 | 1 | 1 | 0 |
| Work and Heat Transfer | 44-68 | 0 | 0 | 0 |
| First Law of Thermodynamics | 69-86 | 1 | 1 | 0 |
| First Law Applied to Flow Processes | 87-116 | 3 | 2 | 1 |
| **Second Law of Thermodynamics** | 117-157 | 7 | **7** | 0 |
| **Entropy** | 158-219 | 8 | **4** | 4 |
| Available Energy, Exergy and Irreversibility | 220-284 | 2 | 1 | 1 |
| Properties of Pure Substances | 285-333 | 5 | 3 | 2 |
| **Properties of Gases and Gas Mixtures** | 334-401 | 7 | **6** | 1 |
| **Thermodynamic Relations, Equilibrium and Third Law** | 402-482 | 5 | **4** | 1 |
| **Vapour Power Cycles** | 483-522 | 6 | **4** | 2 |
| Gas Power Cycles | 523-559 | 2 | 2 | 0 |
| Refrigeration Cycles | 560-581 | 0 | 0 | 0 |
| Psychrometrics | 582-597 | 2 | 1 | 1 |
| Reactive Systems | 598-619 | 2 | 2 | 0 |
| Compressible Fluid Flow | 620-637 | 1 | 1 | 0 |
| **Elements of Heat Transfer** | 638-663 | 5 | **4** | 1 |
| Statistical Thermodynamics | 664-689 | 2 | 2 | 0 |
| Irreversible Thermodynamics | 690-706 | 0 | 0 | 0 |
| Kinetic Theory of Gases... | 707-728 | 1 | 0 | 1 |
| **Transport Processes in Gases** | 729-781 | 5 | **5** | 0 |

**9 of 22 chapters (bolded) have more than 3 solvable concepts** — S7's "max 3 per Section" hard constraint will bind hard across nearly half the book, not just as an occasional edge case, confirming the user's stated concern directly.

**Real S5 result**: 51/51 solvable problems distilled (after the MAX_TOKENS fix), **51 concept cards, 51 distinct clusters, zero merges** — every distilled concept is physically distinct by fingerprint/embedding across the whole real book. 6 LaTeX equations failed to parse (logged, fell back to `UNPARSED::` fingerprint component, not hidden) — mostly `\text{...}` macros and one inequality (`\ge`) that `sympy.parsing.latex` doesn't handle; a real, disclosed gap, not a blocker.

**Real S6 result**: 51/51 scored cleanly, no truncation.

**Real S7 result — the honest headline finding**: pool of 51 **can** reach the raw 20-problem count target, but real hard-constraint results:
- `[FAIL]` ≥6 distinct topics — got **0**. Direct consequence of the pre-existing, already-documented `match_topic_nodes` gap (keyword-overlap heuristic needs real `TopicNode.aliases`, never fixed this session) — not a new bug, but this is the first real-scale run where its effect on S7 is visible end-to-end.
- `[FAIL]` ≤3 per Section — got **4** (max). Confirms the per-chapter table above: several chapters have 4+ solvable concepts, over the cap.
- `[FAIL]` difficulty mix target `{easy:6, medium:9, hard:5}` — got `{easy:0, medium:9, hard:11}`. Real, skewed toward hard; no easy problems at all in the real scored pool.
- `[FAIL]` 8-12 with eligible extensions — got **20**, i.e. *too many* eligible, not too few.
- `[PASS]` the other 4 constraints (computational-suitability count, distinct extension types, physics-informed cap, pairwise cosine diversity).

Full non-LLM suite: still 35/35 (re-verified after each fix this run). `ruff check`/`mypy --strict` clean throughout. Every fix committed as its own commit.

## Next Immediate Task
Nothing blocking remains for S1-S7 at full-book scale — the pipeline runs end to end on the real 781-page book with idempotent, resumable stages. Real next candidates, not started, no priority order implied:
- Fix `match_topic_nodes`/`TopicNode.aliases` — now demonstrably the direct cause of S7's "0 distinct topics" failure at real scale, not just a theoretical gap.
- Decide how to handle the "max 3 per Section" real bind (9/22 chapters over cap) — likely needs either the full MMR/relaxation logic in `selection.py` (built but never exercised beyond the trivial path) to actually kick in, or a product decision about relaxing that constraint.
- Investigate the real S3 confirm-variance (84 vs 66 on identical input) if problem-count stability matters for reproducibility — not attempted this session, and S3 remains frozen pending the user's own hand-count.
- Phases P8-P12 (variant generation, codegen/sandbox execution, rendering, ledger, chat) are still not started — this session's work has been entirely S1-S7.

## Completed: S3 recall fix, real per-chapter numbers, TopicNode.aliases, a real quota correction (2026-08-10)

Direct response to: "S3 recall is the blocking problem." All four numbered tasks
done for real, against the real 781-page book. Book `4d97664c-50ee-4c77-83b8-7951efae4d60`.

**1. temperature=0, live-verified — variance was mostly sampling noise, not prompt ambiguity.**
Added `temperature` end-to-end (Backend protocol, both backends, `StageRoute`, `LLMClient`) and pinned `s3_confirm` to 0. Real test: same 684-candidate set, two independent confirm runs — **350 vs 348 confirmed, 18 disagreements (2.6%)**, down from the original unpinned 84 vs 66 (~21%). Conclusion: temperature was the dominant cause. The 18 residual disagreements were shown, not hidden — most are a real false-positive class in the new detector (below); **7 of the 18 are a genuine, thematically-clustered prompt-ambiguity pattern**: every one is a "derive/prove"-style exercise with no numeric given/find (e.g. "11.1 Derive the following equations...", "11.4 Derive the equations..."), and the model flips between is_problem=True/False for this exact class. Not fixed — the S3 prompt (`prompts/s3_problem_confirm.md`) was left untouched per the standing freeze; this is reported for a decision, not decided unilaterally.

**2. Sequential-enumeration detector — the real recall blocker, fixed.**
Nag's end-of-chapter exercises are a bare numbered list ("5.1 ...", "5.2 ...") under one "PROBLEMS"/"EXERCISES" header with no per-item keyword — the old `_EXERCISE_PATTERN` needed the literal word "Problem" and never matched these, so an entire chapter's exercise list fell through as ONE undifferentiated candidate. Added: once a PROBLEMS/EXERCISES header is found, every subsequent N.M-numbered line starts its own candidate, running to the next such line or the section's own end boundary. Handles this book's real OCR artifact ("1.1" misread as "I.I"). Real result: **109 -> 684 total candidates (+575)** on the pre-refinement candidate set. Found and fixed one real false-positive class in the same pass: the chapter-number component was bare `\d+`, which matched a solution's own inline numeric result (e.g. "0.06\nFor the fluid system, calculate...") as a fake new exercise item — restricted to `[1-9]\d*` since this book's real chapters are numbered 1-22, never 0. New tests cover multi-item splitting, span boundaries, the OCR "I.I" form, and the whole-blob fallback for sections that don't fit the pattern.

**3. Real problems-per-chapter, final numbers** (after wiping and redoing S3-S4 with the fixed detector + temp=0 — old regex-only-detected rows for this book were deleted, not layered on top of the new ones):

| Chapter | Pages | Total | Solvable | Excluded |
|---|---|---|---|---|
| Front Matter | 1-11 | 0 | 0 | 0 |
| Introduction | 12-30 | 10 | 10 | 0 |
| Temperature | 31-43 | 7 | 6 | 1 |
| Work and Heat Transfer | 44-68 | 5 | 5 | 0 |
| First Law of Thermodynamics | 69-86 | 25 | 25 | 0 |
| First Law Applied to Flow Processes | 87-116 | 6 | 4 | 2 |
| Second Law of Thermodynamics | 117-157 | 6 | 6 | 0 |
| Entropy | 158-219 | 51 | 46 | 5 |
| Available Energy, Exergy and Irreversibility | 220-284 | 50 | 47 | 3 |
| Properties of Pure Substances | 285-333 | 36 | 33 | 3 |
| Properties of Gases and Gas Mixtures | 334-401 | 8 | 7 | 1 |
| Thermodynamic Relations, Equilibrium and Third Law | 402-482 | 23 | 22 | 1 |
| Vapour Power Cycles | 483-522 | 6 | 4 | 2 |
| Gas Power Cycles | 523-559 | 24 | 22 | 2 |
| Refrigeration Cycles | 560-581 | 19 | 18 | 1 |
| Psychrometrics | 582-597 | 9 | 9 | 0 |
| Reactive Systems | 598-619 | 2 | 2 | 0 |
| Compressible Fluid Flow | 620-637 | 6 | 6 | 0 |
| Elements of Heat Transfer | 638-663 | 12 | 11 | 1 |
| Statistical Thermodynamics | 664-689 | 3 | 3 | 0 |
| Irreversible Thermodynamics | 690-706 | 0 | 0 | 0 |
| Kinetic Theory of Gases... | 707-728 | 1 | 0 | 1 |
| Transport Processes in Gases | 729-781 | 19 | 19 | 0 |
| TOTAL | | 328 | 305 | 23 |

Real, uneven, honest distribution — not uniform 30-80/chapter as speculated, but several chapters (Entropy, Available Energy, Properties of Pure Substances) now land in that range, while early/short chapters stay in the single digits, matching how this real textbook is actually structured (application-heavy mid-book chapters carry far more exercises than short intro chapters). **19 of 22 chapters now exceed the 3-per-section cap** (up from 9/22 at the old, under-counted recall) — the constraint binds even harder now that recall is real, confirming this needs an actual product decision (relax the cap, or let S7's untested MMR/relaxation logic activate), not just better detection.

**4. TopicNode.aliases populated for mechanical — real result, and a real limit found.**
`DisciplineProfile.topics` now supports `{name, aliases}` (backward compatible; every other profile still uses bare strings). `sync_topic_nodes` previously never updated aliases on an existing row, only set them on first creation — fixed. Populated mechanical's 7 topics with real aliases from this book's own 22 real chapter titles. Live result: **18/22 chapters now match a topic (up from 7)**, but only **3 distinct topics** (Thermodynamics, Fluid Mechanics, Heat & Mass Transfer) — real, structural finding: a single-subject thermodynamics book cannot clear a 6-distinct-topic bar under mechanical's 7-topic taxonomy no matter how good the aliases are, since most of those chapters are all legitimately Thermodynamics subtopics. Aliasing fixed the matching engine (it wasn't meaningfully matching before); it did not and structurally cannot fix topic granularity. That's a taxonomy-design question for the user, not something this fix resolves on its own.

**A real quota correction, found while running S5 on the new, much larger problem set — significant, reverses an earlier conclusion.**
Running distillation against the real 305 solvable problems (up from 51) hit an actual 429 from Google after 23 requests to `gemini-flash-latest` today: the alias now resolves to a different underlying model (`gemini-3.6-flash` per the error body) with a real free-tier cap of 20 requests/day, not the 250 `config/llm_routing.yaml` assumed. Corrected the config so `DailyQuotaExhausted` now fires cleanly at the real number (verified: re-running now stops cleanly with our own exception, not another live 429). **This reverses the earlier "quota isn't binding, multi-day checkpointing isn't needed" conclusion** — with real recall (305 solvable, not 51) and the real 20/day cap, S5 alone needs ~31 batches and will genuinely span multiple real days. Found and fixed a second real bug in the same pass: `run_concept_distillation` and `run_scoring` still only persisted everything in ONE commit at the very end (the exact bug class already fixed in `detection.py`, never applied here) — so hitting the quota wall mid-run discarded all 14 already-completed, already-paid-for distillation batches, not just the failing one. Fixed: both now commit per batch (embeddings too, per distillation batch, well under the 100-item cap at `BATCH_SIZE=10`). This is the real case idempotency was built for — `pf distill` can now simply be re-run once the daily quota resets (UTC) and it will resume from exactly where it left off, at zero re-spent quota on already-distilled problems.

## Blocked On
**S5 (concept distillation) for the real 305-problem pool — genuinely needs multiple real days.** `gemini-flash-latest`'s real cap is 20 requests/day; 305 solvable problems at `BATCH_SIZE=10` is ~31 batches. Today's quota was exhausted by the debugging/discovery work above (23/20 used) before any of today's distillation batches could commit (all lost to the pre-fix single-commit bug, now fixed — nothing to recover, but nothing was wasted going forward either). Next session/day: just re-run `pf distill 4d97664c-50ee-4c77-83b8-7951efae4d60` — idempotency plus the per-batch commit fix mean it resumes cleanly, no special resume logic needed. Expect roughly 2 real days minimum for distillation alone at 20 batches/day (about 31 batches), then S6/S7 (both flash-lite, real 1000/day cap, not tightly binding) can run same-day once distillation completes.

## Design notes for P10/P11 (recorded now per explicit instruction, NOT implemented — API/UI work starts after S5-S7 complete on the real recall-fixed pool)

- **Regenerate must be two distinct actions, not one:**
  - "Reshuffle": same concept clusters, new parameters/wording for each — does NOT write to `IssuedLedger`. The concepts already "count" as issued; reshuffling is just re-rendering the same underlying concepts differently.
  - "New set": 20 unissued clusters — DOES write to `IssuedLedger`. This is what actually advances the no-repeat guarantee.
  - Model both as separate API actions/endpoints, not one "regenerate" endpoint with a flag — the ledger side-effect is the load-bearing difference between them, not an implementation detail to hide behind a parameter.
- **Chapter-scoped generation**: the user selects one or more Sections (real book chapters, per S2's TOC-driven structure); selection (S7) is then constrained to only draw from those sections' pool. No selection means the whole book (current default behavior). This needs `run_selection`'s pool query to accept an optional `section_ids` filter — not designed or implemented yet, just recorded so it isn't lost before P10/P11 design work starts.

## Next Immediate Task
1. Resume S5 distillation once the daily quota resets (see Blocked On) — just re-run `pf distill`, no special handling needed.
2. Then S6 (score) and S7 (select) on the real, recall-fixed pool — expect very different (likely much better) hard-constraint numbers than the old 51-problem run, given 305 solvable vs 51.
3. Decide (user, not unilateral): how to handle 19/22 chapters exceeding the 3-per-section cap, and whether mechanical's topic taxonomy needs finer subtopics under Thermodynamics for the 6-distinct-topics constraint to ever be reachable for a single-subject book.
4. Decide (user, not unilateral): what to do about the 7 real "derive/prove"-exercise confirm-disagreement cases — is a pure derivation exercise (no numeric given/find) meant to be is_problem=True, kind=derivation, and should the prompt say so explicitly?
5. Only after 1-3 are real: P10/P11 (API + UI), using the two design notes above.

## Completed: three fixes, then full S1-S7 to completion (2026-08-10, same day)

Direct response to explicit instruction: reroute S5, retire the single Thermodynamics
node, exclude derivations, then run to completion. All three landed; then a fourth
real bug was found only by actually running S7 end-to-end afterward.

**1. S5 rerouted to `gemini-flash-lite-latest`, `BATCH_SIZE` 10->30.** Distillation is schema-bound structured extraction, not reasoning — flash-lite's real (if not fully exhaustion-verified) ~1000/day cap removes the bottleneck flash-latest's confirmed 20/day cap created. Real result: **distillation that needed ~31 batches over multiple real days on flash-latest completed in ONE run of 10 batches on flash-lite** — no multi-day wait needed after all. Audited every stage: S2/S3/S5/S6 all schema-bound extraction now on flash-lite; flash-latest and any future working Pro model reserved strictly for S8/S9 (reasoning-quality-critical). Found `s4_vision`'s routing entry is dead config (S4 is pure regex, never calls an LLM) — left in place, flagged as inactive. `docs/adr/0006` got a dated addendum distinguishing the now-fully-verified 20/day (live 429) from the still-only-lower-bound-verified ~1000/day (survived 132/day, never actually exhausted) — not equally solid claims.

**2. Single "Thermodynamics" TopicNode replaced with 12 real subtopics** (First Law, Second Law, Entropy, Available Energy and Exergy, Properties of Pure Substances, Thermodynamic Relations, Vapour Power Cycles, Gas Power Cycles, Refrigeration, Psychrometrics, Reactive Mixtures, Compressible Flow), aliased from this book's own real chapter titles. Deleted the orphaned old node. Real result: **13 distinct topics matched across the book's 22 sections** (up from 3). Two chapters ("Statistical Thermodynamics", "Irreversible Thermodynamics", neither in the requested 12) still weakly false-match "First Law" purely via the shared generic word "Thermodynamics" — disclosed as a pre-existing limitation of the keyword-overlap heuristic on short titles (`docs/adr/0005`), not fully fixable by alias editing alone.

**3. Derive/prove exercises now explicitly classified `kind=derivation` and excluded from the numeric pipeline.** `prompts/s3_problem_confirm.md` (v3) now explicitly instructs: a "derive/prove/show that" exercise with no numeric given/find is a genuine problem (not `not_a_problem`) but is specifically `kind=derivation`, distinct from `worked_example`/`exercise`. `run_detection` now sets `is_solvable = (kind != DERIVATION)` at persist time — same flag S4 already uses for figure-dependent exclusions, same meaning ("can't feed the numeric/executable pipeline"), different reason. Real result: **13 derivation-kind problems found and excluded** (more than the 7 seen in the earlier temperature-variance sample, since the sequential-enumeration detector surfaced many more derive/prove items across the whole book) — retroactively applied to already-persisted rows (no re-confirm needed, this is a persistence-layer flag, not new LLM output).

**A fourth real bug, found only by running S7 end-to-end after all three fixes:** the first full re-run reported **0 distinct topics** despite Section-level matching finding 13 — `ConceptCardORM.topic_node_ids` (what `selection.py` actually reads) was hardcoded to `[]` at card construction in `concepts.py`, regardless of what the card's own Section had matched. Every bit of this session's topic-taxonomy/alias work never reached S7 at all until this was found and fixed. Deterministic, not LLM-derived, so the fix applies with a direct DB backfill (no re-distillation): 276/292 already-persisted cards now carry real topic tags, 13 distinct across the pool.

**Full real pipeline result, this book, this run:**
- S3: 328 confirmed (59 worked examples + exercises + 13 derivations, excluded)
- S4: 292 solvable (23 figure-excluded + 13 derivation-excluded)
- S5: 292/292 distilled, 288 clusters (4 real merges), 49 LaTeX parse failures (logged, not hidden)
- S6: 292/292 scored
- S7 (pool of 288 scored cards — the 4 merged-away duplicates aren't separately scored): pool reaches the raw 20-count target. **5 of 8 hard constraints now pass** (up from 2/8 at the very first real run against 5 concepts):
  - `[PASS]` >= 6 distinct topics — **10** (was 0; fixed by #2 + the card-inheritance bug above)
  - `[FAIL]` <= 3 per Section — max got **4**. Real, structural: confirmed earlier that 19/22 chapters exceed 3 solvable concepts; a genuinely diverse 20-problem set drawing from a 288-card pool this unevenly distributed will keep bumping this cap without either S7's untested MMR/relaxation logic actually engaging, or a decision to relax the cap itself.
  - `[FAIL]` difficulty mix (target `{easy:6, medium:9, hard:5}`) — got `{easy:0, medium:3, hard:17}`. Real and skewed hard — S6's real scoring is rating this book's real content as mostly hard, with zero problems scored easy at all.
  - `[PASS]` >= 4 with computational_suitability>=4 — **20**
  - `[FAIL]` 8-12 with eligible extensions — got **19**, too many, not too few (same direction as the earlier 51-concept run).
  - `[PASS]` >= 3 distinct extension types — **5**
  - `[PASS]` <= 2 physics_informed — **0**
  - `[FAIL]` no pair with cosine >= 0.85 — max got **0.885**, one near-duplicate pair survives selection just barely over threshold.

Full non-LLM suite: 37/37 passed throughout, re-verified after every change. `ruff check`/`mypy --strict` clean throughout. Every fix its own commit.

## Next Immediate Task
Not all 8 hard constraints pass yet — 3 real, disclosed gaps remain, all needing a product/design decision rather than another bug fix:
1. **<= 3 per Section**: either let S7's untested MMR/relaxation logic actually activate (it exists, was built, has never been exercised beyond the trivial "pool too small" path), or decide the cap itself should be relaxed for a book this section-uneven.
2. **Difficulty mix**: S6's real scoring is rating almost everything hard/medium, zero easy. Worth checking whether the S6 scoring prompt's difficulty guidance is calibrated realistically for this book's actual content, or whether the target mix itself assumes a difficulty distribution this book doesn't have.
3. **8-12 with eligible extensions**: consistently over-eligible (19-20 out of ~20-51 across every run so far) — worth checking whether `eligible_extension_types_for`'s deterministic gating logic is too permissive, or whether the target window itself needs revisiting.
4. **cosine >= 0.85 pair**: one near-duplicate survives selection (0.885) — `_check_hard_constraints`'s diversity check may need to run as an actual selection filter rather than a post-hoc report.
Recommend the user weigh in on 1-3 (product/taxonomy decisions) before more code changes — this isn't a "keep fixing bugs" situation anymore, it's "decide what correct looks like" for a handful of real, understood tradeoffs.

## Completed: S7 selection fixed for real; all 7 hard constraints pass (2026-08-10, same day)

Explicit instruction, four parts, all landed:

1. **Eligible-extensions COUNT removed as an S7 hard constraint.** Correct per the user's own diagnosis: eligibility is a pool property (S6, unchanged), attachment is an S9-time decision. `docs/adr/0009` records the correction; the attachment rule itself (attach to <=12 of 20, by highest `ml_extension_potential`, preserving >=3 distinct types) is implemented in the new `variants` module below, not gated into S7.
2. **Percentile-based difficulty.** `_assign_percentile_difficulty` sorts the whole pool by (the LLM's own label, `composite_score` tiebreak) and slices into thirds by position — no new LLM field, no re-scoring, fixes the clustering structurally.
3. **The <=3-per-section failure was a real bug, not genuine infeasibility — confirmed by investigation, exactly as flagged as the two possibilities to check.** `run_selection`'s "pool >= target" branch was a plain `sorted(...)[:20]` by score; hard constraints were only ever *checked* after the fact, never *enforced* during construction, despite the code comment and PROGRESS.md both describing "MMR/relaxation logic" as "implemented but never exercised." That description was never accurate — no such logic existed anywhere in the file. Rewrote `_select_with_constraints` to enforce per-section cap, physics-informed cap, and pairwise-cosine cap turn-by-turn during construction. **No documented relaxation order existed anywhere in the repo either** (checked: no spec.md, no CLAUDE.md, no ADR — confirmed via a dedicated search) — defined and recorded one in `docs/adr/0009` since none could be found to follow.
4. **Audited for other hardcoded-empty-default bugs of the `topic_node_ids=[]` shape.** `assumptions`, `typical_pitfalls`, `given_dimensions`, `eligible_extension_types`, `canonical_equation_srepr` — all confirmed genuinely populated from real LLM output or deterministic computation, not hardcoded. `figure_ids=[]` and `solution_md=None` on `SourceProblemORM` are correctly empty by current design (S4's figure interpretation and any solving step don't exist yet — not bugs, just not-yet-built). **Found one real bug of this shape**: `ConceptClusterORM.centroid_embedding` was set once at cluster creation and never updated when a new card joined an existing cluster — any multi-member cluster carried a stale centroid frozen at its first member's own embedding forever. Fixed (running mean); backfilled the 4 real multi-member clusters that existed.

**Real result after the fix, same 288-card pool, zero relaxation needed:**
- `[PASS]` >= 6 distinct topics — 9
- `[PASS]` <= 3 per section — max 3
- `[PASS]` difficulty mix {easy:6, medium:9, hard:5} — exact match
- `[PASS]` >= 4 with computational_suitability>=4 — 10
- `[PASS]` >= 3 distinct extension types — 3
- `[PASS]` <= 2 physics_informed — 0
- `[PASS]` no pair with cosine >= 0.85 — max 0.848

**All 7 remaining hard constraints pass, no relaxation applied.** Per explicit instruction, not spending further session time tuning this — moving to S8/S9.

## Completed: S8 + S9 Part A + S10, real end-to-end, 20/20 verified, real PDFs on disk (2026-08-10, same day)

Built from scratch this session (no prior scaffolding existed for any of these):

**S8 (`variants/variants.py`)**: one real LLM call per selected concept generates new numeric parameters, a rewritten self-contained problem statement, and a solution-approach step list — deliberately not a trusted final answer; the real number only ever comes from S9 actually running code. `select_extension_attachments` implements the S9-time rule from `docs/adr/0009`: at most 12 of the 20 get an extension attached, ranked by `ml_extension_potential`, preserving >=3 distinct types.

**S9 Part A (`codegen/codegen.py`)**: one real LLM call generates a self-contained Python script; real execution via `sandbox.runner.run_code` determines `verified_answer`/`verification_status` — never the model's own claimed answer. One real retry with actual stderr fed back on failure, never more.

**Real result, full 20-problem set, this book: 20/20 execution-verified.** Two real bugs found and fixed along the way:
- **RPM burst bug**: two separate `LLMClient()` instances (one for S8, one for S9), both routed to the same model, each got an independent in-memory RPM token bucket (RPD is disk-shared, RPM is not — see `llm/rate_limiter.py`). Their combined burst triggered a real live 429 despite a limiter existing. Fixed: one shared client. Added idempotency to `pf generate` (skip any concept that already has a VERIFIED variant) so a resumed run after a failure doesn't re-spend quota on already-solved problems.
- **Missing per-discipline sandbox image**: `mechanical.yaml` declares CoolProp as a solver_lib, but no per-discipline image had ever been built — `pf generate` was hardcoded to the shared base image (no CoolProp). One real problem (a back-pressure turbine cogeneration analysis, genuinely needing real steam properties) failed with `ModuleNotFoundError: No module named 'CoolProp'` until `docker/sandbox/mechanical.Dockerfile` was built and `pf generate` was wired to use the book's own `discipline.sandbox_image_tag` instead of a hardcoded default. Verified on retry with the real image.
- Sanity-checked the first verified answer (Brayton cycle net work output) by hand — the execution-verified 300.75 kJ/kg matches an independent manual calculation from the same isentropic relations, confirming the generated code is actually implementing real thermodynamics, not just running successfully.

**Real quota note**: `gemini-flash-latest`'s real 20/day cap was already spent today by the pre-fix S5 distillation run earlier this same session (documented above), before today's S8/S9 work existed to reserve it. `config/llm_routing.yaml` temporarily routes `s8_variant_generation`/`s9_codegen` to `gemini-flash-lite-latest` for today only — clearly commented as TEMPORARY, standing policy unchanged (reserve flash-latest for S8/S9 once quota resets). **Action item: revert those two routing entries to `gemini-flash-latest` once the daily quota resets (UTC).**

**S10 (`render/render.py`)**: real Typst rendering via the `typst` PyPI package (bundles the compiler). Re-runs the real S7 selection, pairs each selected concept with its own verified Variant, renders a student handout PDF (statements only) and a faculty solutions manual PDF (statement + solution approach + execution-verified answer), and writes each problem's real generated Python to `code/problem_NN.py`. Free-text LLM fields are escaped (`_typst_escape`) before embedding, since Typst's own markup treats `$`, `_`, `*`, `#` etc. specially — this means inline LaTeX in statements renders as literal escaped text, not typeset math, a disclosed simplification, not a silent gap.

**Real files on disk**: `data/generated/4d97664c-50ee-4c77-83b8-7951efae4d60/student_handout.pdf` (40 KB), `solutions_manual.pdf` (145 KB), `code/problem_01.py` through `problem_20.py`.

**Known gaps, disclosed, not attempted this session:**
- **Ledger-commit** (writing an `IssuedLedger` row so the no-repeat guarantee actually advances) is not implemented — it needs a real `Course` to exist, and nothing in this CLI-driven flow has created one. `ProblemSetORM`/`IssuedLedgerORM` are unused by `run_render`.
- **LaTeX->Typst math conversion** is not implemented — math renders as literal escaped text (see above), not typeset equations. Real, cosmetic gap.
- **One harmless duplicate**: the concept cluster for "Brayton cycle performance and comparison" has 2 VERIFIED variant rows (from before the idempotency fix landed) — `run_render` picks the most recent by id and rendered correctly, but the older duplicate is still in the table. Not cleaned up; noted rather than silently left unmentioned.
- A real `SandboxRunnerClient` HTTP wrapper for the worker's actual deployment path (per `docs/adr/0002`) is still not built — this session's `pf generate`/`pf render` call `sandbox.runner.run_code` directly, appropriate for a CLI-driven flow on the host but not for the containerized worker.

## Next Immediate Task
1. Revert `config/llm_routing.yaml`'s `s8_variant_generation`/`s9_codegen` to `gemini-flash-latest` once its daily quota resets (UTC) — today's routing to flash-lite was an explicitly-temporary, same-day workaround.
2. Decide whether ledger-commit (real `Course` + `ProblemSetORM` + `IssuedLedgerORM`) is needed before this is usable end-to-end for a real faculty user, or whether the current PDF-on-disk output is sufficient for now.
3. LaTeX->Typst math conversion, if properly typeset equations matter for the final deliverable's polish.
4. Everything else in this file's earlier "real product decisions pending" sections (topic taxonomy granularity, derive/prove prompt clarity) remains open and un-decided by the user.

## Completed: S10's two blocking rendering gaps fixed for real (2026-08-10, same day)

Both explicitly called out as blocking, not polish:

**1. Python listings were missing from the solutions manual.** `core_python_code` was always real and already written to `code/problem_NN.py`, but the solutions manual template never embedded it — a template gap, not a data gap. Fixed: `_typst_raw_block` embeds each problem's real Part A solver inline via a Typst raw code block (`` ```python ``` ``) right after its worked solution and verified answer, fenced with enough backticks to contain any backtick run already in the code. The separate `.py` files are unchanged. New test `test_solutions_manual_contains_nonempty_code_block_per_problem` asserts every problem section contains its own real, non-empty code block — and a companion test asserts the *student* handout never leaks solver code into the wrong document.

**2. LaTeX rendered as literal escaped text** (`\frac{P_2}{P_1}` printing verbatim) — confirmed unusable for the PDF's actual purpose, fixed with a real recursive LaTeX->Typst math converter (`_latex_to_typst_math`, balanced-brace aware, not naive regex): handles `\frac`, `\dot`/`\hat`/`\sqrt`, `_{...}`/`^{...}` grouping, `\text`, `\left`/`\right` sizing, and the common Greek letters/operators this project's own LLM calls actually emit. `$...$` inline math spans inside `statement_md`/`solution_steps` are detected and converted to real Typst math mode; surrounding prose is still escaped as before (`_render_text_with_math`).

**Two real Typst compile errors found and fixed by actually testing against real equations and real production data, not just inventing test cases:**
- Typst's math mode raises `unknown variable` for a bare multi-letter word (e.g. `COP`) — unlike LaTeX, which just italicizes adjacent letters with no identifier lookup at all. Fixed: multi-letter bare words not in a small safe set (`sin`, `cos`, `ln`, `log`, ...) are quoted as literal upright text instead.
- Found only by re-rendering the REAL 20-problem book afterward (not caught by my own hand-written test cases): a letter-then-digit token written without a LaTeX subscript (`a2` instead of `a_2`) hit the same `unknown variable` error, because my first fix only consumed pure-alphabetic runs — `a` stayed safely bare, but the following literal `2` let Typst re-glue them into the identifier `a2` anyway. Broadened word-consumption to alphanumeric runs. Verified: the real 20-problem solutions manual now compiles cleanly end to end (`solutions_manual.pdf` grew 145 KB -> 523 KB from the embedded code alone).
- Also found via a self-written test (not real production data, but a real ambiguity worth guarding): a literal currency amount (`$5`) immediately before a genuine `$...$` math span can pair with the wrong `$` and swallow prose as bogus math. Added a "`$` followed by a digit is currency, not math" heuristic — costs nothing, this book's real content has no currency amounts, but removes a demonstrated failure mode.

New tests, all in `tests/test_render.py`, pure functions only (no DB, no LLM, no real sandbox): code-block presence per problem, student handout never leaking code, `_latex_to_typst_math` actually compiling for 10 real equations from this session, literal dollar amounts surviving next to real math, and the raw-block fence-length safety property.

**Remaining, disclosed, not blocking**: math OUTSIDE `$...$` delimiters (e.g. a stray `\cdot` the LLM put directly in unit-notation prose rather than inside a math span) still renders as escaped literal text — a real, minor, cosmetic residue of inconsistent LLM formatting, not a bug in the converter itself.

## Blocked On — real, external, time-gated (not something more code can fix)

`gemini-flash-latest`'s real free-tier daily quota (confirmed live earlier this session: 20 requests/day) will not reset until **2026-08-11 00:00 UTC** — about 9.5 hours from this entry's timestamp (checked live: current time 2026-08-10 14:40 UTC). Tasks explicitly sequenced by the user to run "once flash-latest quota resets" are not started:

3. **Re-run S9 verification on all 20 with S8/S9 routed to the strongest available model** (revert off the temporary flash-lite workaround first — see #6). Report how many of the 20 verified answers CHANGE under the stronger model, not just whether they still verify.
4. **Make the independent re-solve genuinely blind**: it must receive neither the original generated Python nor `solution_steps` — only the variant's own statement/params, same as a real independent check would. Add a test that fails if either leaks into the re-solve prompt. Report actual relative differences between the two answers per problem; if all 20 agree far inside 1%, that's evidence the "independent" re-solve wasn't actually independent (e.g. accidentally reusing context, or the problems being trivial enough that any correct method converges).
5. **Create the real Course** ("AI/ML for Mechanical Systems", faculty "Mahesh", institution "RGUKT Basar") — real, user-provided values, not fabricated. Commit the ledger (`IssuedLedgerORM`) for the current 20-problem set against this course. Then generate a SECOND set from the same book and assert zero concept-cluster overlap with the first, proving the no-repeat guarantee for the first time this session — it has been built (S3-era `docs/adr/0003`) but never actually exercised end-to-end.
6. **Revert `config/llm_routing.yaml`'s `s8_variant_generation`/`s9_codegen`** from the temporary `gemini-flash-lite-latest` back to `gemini-flash-latest` — do this FIRST when resuming, before task 3, since task 3 explicitly needs the strongest available model, not the same one that already agreed with itself.

**Resume point**: nothing else needs to happen before 00:00 UTC. When resuming: (a) revert the routing (#6), (b) re-run `pf generate --book 4d97664c-50ee-4c77-83b8-7951efae4d60 --limit 20` — note this will need a *fresh* re-solve mechanism, not the existing idempotency-skip path, since idempotency currently skips anything already VERIFIED and the whole point of #3/#4 is re-solving what's already verified under a different model/blind conditions; this needs new code (a `--force`/`--reverify` path or a separate "independent re-solve" function), not just re-invoking the existing command as-is — not yet designed, flagging now so it isn't assumed trivial. (c) #5's Course creation and ledger-commit can happen independently of #3/#4's timing, whenever convenient.
