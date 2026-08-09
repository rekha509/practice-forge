<!-- version: 1 -->
<!-- used by: src/practice_forge/concepts/concepts.py (S5 concept distillation) -->
<!-- model: routed via config/llm_routing.yaml, stage "s5_distillation" -->

You are distilling the underlying physics concept from a solved engineering
problem, so that problems testing the SAME governing equations and method
can later be recognized as duplicates of each other regardless of wording
or numbers.

For EACH problem below, extract:
- name: a short human-readable name for the concept (e.g. "Steady flow
  energy equation applied to a nozzle").
- governing_equations_latex: the core equation(s) that must be applied to
  solve this problem, as LaTeX strings (e.g. "\\frac{V_1^2}{2} + gz_1 + h_1
  = \\frac{V_2^2}{2} + gz_2 + h_2 + q - w"). Use the same symbols the
  problem itself uses where possible.
- assumptions: the physical assumptions the solution relies on (e.g.
  "steady flow", "no potential energy change", "ideal gas").
- solution_strategy: one or two sentences on the method used to go from
  the given quantities to the answer.
- typical_pitfalls: 1-3 common mistakes a student might make on this type
  of problem.
- given_dimensions: the physical dimension of each given quantity, in
  bracket notation, e.g. "[mass]/[time]", "[pressure]", "[length]/[time]",
  "[temperature]". One entry per given quantity, not per problem.
- solve_for_dimension: the physical dimension of what's being solved for,
  same bracket notation.
- method_tag: a short machine-readable slug for the solution method, e.g.
  "steady_flow_energy_equation" or "ideal_gas_polytropic_process".
- continuous_param_count: how many of the given quantities are continuous
  numeric parameters with a meaningful physical range (not counts, not
  booleans) — this gates whether an ML teaching extension could later be
  attached to this problem (a surrogate model needs >= 2).
- has_degradation_mode: true only if the problem involves a quantity that
  plausibly degrades/drifts over time or usage (e.g. fouling, wear,
  efficiency loss) — most single-instant thermodynamics problems do not.
- has_design_tradeoff: true only if there's a genuine competing-objectives
  design choice implied (e.g. minimize mass subject to a stress limit) —
  most solved textbook examples do not.
- has_tolerance_spec: true only if any given quantity has a realistic
  manufacturing/measurement tolerance the problem itself discusses — most
  do not.

Do not guess values you cannot see in the problem text. If a field
genuinely doesn't apply, use an empty list/false/0 as appropriate rather
than inventing content.

Return a JSON array with exactly one object per problem, one per index
below. Copy each problem's own "index" value into your object for it.

Problems:
{problems_block}

Respond with the requested JSON only.
