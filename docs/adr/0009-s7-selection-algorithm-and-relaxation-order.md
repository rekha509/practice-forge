# 9. S7 real constrained selection: algorithm, relaxation order, and the eligible-extensions correction

## Status
Accepted

## Context
The first real end-to-end run of S7 against a pool of 288 scored concepts
reported `<= 3 per section` as FAILED with a max of 4 — despite 20
problems needing only 7 of 22 real sections represented, which should be
trivially satisfiable. Investigating found the actual bug: the "pool >=
target" branch of `run_selection` was a plain `sorted(...)[:20]` by
`composite_score`, with hard constraints only *checked* afterward, never
*enforced* during construction. The docstring and PROGRESS.md both
described "full MMR/relaxation logic" as "implemented but never exercised"
— that description was aspirational, not accurate; no such logic existed
anywhere in the file.

Separately, S7's difficulty-mix constraint (target `{easy:6, medium:9,
hard:5}`) was measured failing badly on real content — `{easy:0, medium:3,
hard:17}` — because S6's LLM-assigned absolute difficulty label clusters
toward hard/medium on this book's real content and will never naturally
produce that spread no matter how selection is tuned around it.

Also, the `8-12 with eligible extensions` hard constraint was itself a
design mistake, identified by the user: extension *eligibility* is a
property of the scored pool (computed deterministically in S6 from a
card's own gating fields — `scoring.eligible_extension_types_for`), but
whether an extension is actually *attached* to a generated variant is a
decision that belongs at S8/S9 time, once the actual 20-problem set is
known — not something S7's selection should gate the set's composition on.

## Decision

**1. Real constrained selection, hard filters enforced during construction.**
`_select_with_constraints` (selection.py) builds the 20-problem set with
per-section count, physics-informed count, and pairwise-cosine-similarity
tracked and enforced turn-by-turn as candidates are considered — a
candidate that would violate any of the three is skipped, not selected
then reported as a violation afterward.

**2. Percentile-based difficulty, not the LLM's absolute label.**
`_assign_percentile_difficulty` re-derives each pool member's difficulty
tier by sorting the WHOLE pool on `(the LLM's own easy/medium/hard label,
composite_score as tiebreak)` and slicing into thirds by position. This
keeps the LLM's real relative judgment (something it called "hard" still
outranks something it called "medium" within a tier, most of the time)
while fixing the clustering structurally — a percentile split is
well-distributed by construction, with no new LLM field and no re-scoring
required. Selection then builds toward the 6/9/5 target using these
percentile tiers, not the raw label.

**3. Declared relaxation order** (previously referenced in a code comment
but never actually specified anywhere — corrected here, not carried
forward as-is):
   1. **Difficulty mix** (exact 6/9/5 split) — relaxed first if a tier runs
      out of constraint-respecting candidates; backfill from the remaining
      pool by `composite_score`, logged as a relaxation.
   2. **Pairwise cosine diversity** (< 0.85) — relaxed next, only if the
      set would otherwise come in under `TARGET_SET_SIZE` after (1).
   3. **Distinct topics (>= 6)**, **distinct extension types (>= 3)**,
      **computational-suitability count (>= 4)** — not actively relaxed by
      code; these are diversity/coverage properties that emerge from
      spreading selection across sections (forced by the per-section cap)
      rather than being directly targeted, and are reported as real
      pass/fail against the pool's actual composition.
   4. **Per-section cap (<= 3)** and **physics-informed cap (<= 2)** —
      never relaxed. These are treated as genuine correctness constraints
      (don't over-represent one chapter; don't over-issue the "rare, gate
      hard" physics-informed extension), enforced as hard filters with no
      relaxation path. If a pool is ever too thin to fill 20 problems
      without violating either, that is reported as `can_reach_target
      failing to reach 20`, not a silently-violated cap.
   Any relaxation actually applied is recorded in
   `SelectionResult.relaxations_applied` and echoed by `pf select` as
   `[RELAXED] ...` lines — never silent.

**4. Eligible-extensions COUNT removed as an S7 hard constraint.**
`EXTENSION_RANGE = (8, 12)` and its check are deleted from
`_check_hard_constraints`. Eligibility itself (`CandidateScore.
eligible_extension_types`, computed in S6) is unchanged and still feeds
the (retained) `>= 3 distinct extension types` diversity check. What
extensions actually get *attached* to a generated variant is now an
S9-time decision: `variants.select_extension_attachments` attaches an
extension to at most 12 of the 20 selected problems, chosen by highest
`ml_extension_potential`, while preserving `>= 3` distinct extension types
among the attached set — implemented where variants are actually
generated, not gated into the pool-selection step.

## Consequences
- `run_selection`'s pool->=target branch now does real work; the previous
  "not exercised in this run" framing in PROGRESS.md and this module's own
  docstring was accurate only by accident (the pool never reached 20 in
  earlier sessions) and is retired.
- `SelectionResult` gained `relaxations_applied: list[str]` — any caller
  reporting a `SelectionResult` should surface this alongside
  `constraints_satisfied`, not just the pass/fail table, or a relaxed
  constraint could be misread as satisfied.
- The eligible-extensions constraint's removal means S7's constraint table
  is now 7 checks, not 8 — anyone comparing constraint counts against
  earlier PROGRESS.md entries (which cite "8 hard constraints") should read
  this ADR first.
