<!-- version: 2 -->
<!-- used by: src/practice_forge/verification/blind_resolve.py (S9 blind re-solve) -->
<!-- model: routed via config/llm_routing.yaml, stage "s9_blind_resolve" —
     DELIBERATELY a different model than stage "s9_codegen" (see
     blind_resolve.py's BlindResolveModelCollisionError), so a systematic
     error in one model can't "confirm" itself. -->
<!-- v2: v1 asked for "ANSWER <name>: <value> <unit>" lines only, but real
     responses routinely ignored that and returned full derivations
     (LaTeX, Python snippets) anyway -- confirmed live: free-text scanning
     over that then matched intermediate scratch-work numbers against the
     solver's answer, burying the one real match under noise. Asking for a
     single trailing JSON object is enforced by parsing, not just asked
     for: blind_resolve.py rejects and retries once on anything else. -->

You are an independent second solver checking a colleague's work. You have
NOT seen their solution, their code, or their reasoning — only the
original problem. Solve it yourself, from scratch.

Problem:
{statement_md}

Given parameters (already-parsed values from the problem statement — use
these directly, do not re-derive them from the prose):
{params}

Work through the physics and compute every requested quantity numerically.
You may show your working.

Then, as the LAST thing in your response, output a single JSON object —
and nothing after it — mapping each requested quantity's name to its
numeric value and unit, in exactly this shape:

{"quantity_name": {"value": <number>, "unit": "<unit string>"}, ...}

For example:
{"net_work": {"value": 300.75, "unit": "kJ"}, "cycle_efficiency": {"value": 0.583, "unit": "dimensionless"}}

Do not wrap it in a markdown code fence. Do not add any text after it.
