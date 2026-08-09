# 7. S4 descoped to detect-and-exclude for v1 — no figure interpretation

## Status
Accepted

## Context
The spec's S4 calls for cropping figures and sending them to a vision
model (Sonnet, originally) to produce `structured_spec_json` (beam
supports/spans/loads, circuit topology, etc.), dropping only what falls
below a confidence threshold. Two things make that not viable right now:

1. **Free-tier vision cost.** A single tiny 200x100 synthetic test image
   cost 1081 input tokens against `gemini-flash-latest` (measured live,
   see `docs/adr/0006`). Real cropped textbook figures — larger, more
   detailed, often needing higher resolution to read scale markings and
   labels — will cost more per call. Against a ~250 request/day budget on
   that model, even a modest per-book figure count makes batched vision
   calls impractical without either burning most of the day's quota on
   figures alone or accepting a resolution too low to trust.
2. **Quality risk on scanned diagrams.** This project's real content is
   scanned/OCR'd textbook pages (see `docs/adr` on `nag_real.pdf`), not
   clean digital figures. A vision model's reconstruction of a beam
   diagram's exact spans, loads, and support conditions from a scanned,
   possibly skewed or noisy image is a plausible-but-wrong failure mode —
   and the spec is explicit that a wrong reconstruction is worse than
   excluding the problem: "Figure-dependent problems must be resolved or
   dropped, never guessed... Never invent geometry or loading."

Given both, attempting interpretation now would either overspend the
day's Gemini quota or risk exactly the failure mode the spec forbids.

## Decision
S4 is descoped for v1 to **detection and exclusion only**:
- `src/practice_forge/figures/figures.py` classifies each `SourceProblem`'s
  `figure_dependency` from its **statement text alone** (see that module's
  docstring for why `Page.has_figure` is useless here — every page of a
  scanned book is one raster image, so it's `True` unconditionally).
  Deliberately binary and conservative: any figure/diagram reference in the
  text -> `ESSENTIAL`, everything else -> `NONE`. No `DECORATIVE` bucket —
  distinguishing decorative from essential needs seeing the figure, which
  this stage doesn't do, so an ambiguous case defaults toward exclusion,
  not inclusion.
- Every `ESSENTIAL` problem gets `is_solvable = False` and is excluded from
  everything downstream (S5 distillation, S6 scoring, S7 selection) by that
  flag — no code elsewhere needs to know S4 was skipped.
- The `Figure` table and the module boundary (`run_figure_descope`) stay in
  place as the integration point for real interpretation later — swapping
  in actual crop+vision only touches this one module.

## Consequence for the P4 gate
Changed from "figures are interpreted with N% confidence-calibrated
accuracy" to: **figure-dependent problems are correctly DETECTED and
EXCLUDED.** Verified by: every `SourceProblem` whose statement references a
figure has `figure_dependency=ESSENTIAL` and `is_solvable=False`; every
other problem is unaffected (`figure_dependency=NONE`, `is_solvable`
untouched by this stage).

## Consequences
- Real figure-dependent problems from real textbooks are simply lost from
  the candidate pool for v1 — accepted explicitly, since a dropped problem
  is a correct, honest outcome and a fabricated-geometry problem is not.
- The text-only classifier will have false positives (a problem mentioning
  "as shown" in a way that doesn't actually require figure data) and is
  conservative by design about that tradeoff — see the module docstring.
  Not measured against labelled ground truth in this run (no human labels
  exist yet for `nag_real.pdf` — see the P3 unvalidated-accuracy note this
  session also recorded).
- When real interpretation is eventually built, `run_figure_descope`'s
  classification step is replaced by real crop+vision+schema logic that
  also has the option to *resolve* an `ESSENTIAL` problem (set
  `structured_spec_json`, keep `is_solvable=True`) rather than only ever
  excluding it — today it can only exclude.
