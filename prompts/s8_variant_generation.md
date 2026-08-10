<!-- version: 1 -->
<!-- used by: src/practice_forge/variants/variants.py (S8 variant generation) -->
<!-- model: routed via config/llm_routing.yaml, stage "s8_variant_generation" -->

You are generating a NEW variant of an engineering problem for a practice
set. You are given the underlying CONCEPT (governing equations, method,
assumptions) and the ORIGINAL real textbook problem it was distilled from,
for realism and context only — do not copy its numbers or its wording.

Concept:
Name: {name}
Governing equations (LaTeX): {equations}
Method: {method_tag}
Assumptions: {assumptions}
Given quantity types (what the problem must supply numeric values for): {given_dimensions}
Solve for: {solve_for_dimension}

Original real problem (context only — do not reuse its numbers or sentences):
{original_statement}

Generate ONE new problem:
- new_params: a JSON object of new given numeric values — one key per
  given quantity type above, with realistic engineering magnitudes and
  units for this kind of problem. Vary them substantially from the
  original (not a small perturbation), while staying physically sensible
  for the stated assumptions (e.g. temperatures/pressures/ratios in a
  range where the underlying equations remain valid).
- statement_md: a complete, self-contained problem statement written
  around new_params' own values, asking for the same solve_for
  quantity/quantities the original problem asked for.
- solution_steps: a list of short strings, each one step of the intended
  SOLUTION APPROACH (which equation/method to apply, in order). Do not
  state a final numeric answer here — an independent program will compute
  the real answer by actually running code, not by this step list being
  trusted as ground truth.

Respond with a single JSON object: {"new_params": {...}, "statement_md":
"...", "solution_steps": ["...", ...]}. Respond with the requested JSON
only.
