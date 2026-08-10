<!-- version: 1 -->
<!-- used by: src/practice_forge/codegen/codegen.py (S9 Part A: core solver) -->
<!-- model: routed via config/llm_routing.yaml, stage "s9_codegen" -->

Write a single, self-contained Python script that solves the engineering
problem below by actually computing the answer numerically — not by
asserting a result.

Concept method: {method_tag}
Governing equations (LaTeX, for reference): {equations}
Assumptions: {assumptions}

Problem (solve exactly this, using ONLY the numbers given in it):
{statement_md}

Given parameters (already-parsed values from the problem statement — use
these directly, do not re-derive them from the prose):
{params}

Requirements:
- Use only the Python standard library plus: numpy, scipy, sympy, pint.
  {extra_libs_note}
- The script must run standalone with `python -c "<script>"` — no file
  I/O, no network, no input().
- Compute every requested quantity numerically from the given parameters.
- Print each final result on its own line in the exact form
  `RESULT <name>: <value>` (e.g. `RESULT cycle_efficiency: 0.583`) — one
  line per requested quantity, plain numbers (no units in the printed
  value itself, use SI base units throughout the calculation).
- Do not print anything else after the RESULT lines that could be mistaken
  for one.

{retry_note}

Respond with the Python code only, no markdown fences, no explanation.
