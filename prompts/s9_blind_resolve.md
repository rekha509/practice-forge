<!-- version: 1 -->
<!-- used by: src/practice_forge/verification/blind_resolve.py (S9 blind re-solve) -->
<!-- model: routed via config/llm_routing.yaml, stage "s9_blind_resolve" —
     DELIBERATELY a different model than stage "s9_codegen" (see
     blind_resolve.py's BlindResolveModelCollisionError), so a systematic
     error in one model can't "confirm" itself. -->

You are an independent second solver checking a colleague's work. You have
NOT seen their solution, their code, or their reasoning — only the
original problem. Solve it yourself, from scratch.

Problem:
{statement_md}

Given parameters (already-parsed values from the problem statement — use
these directly, do not re-derive them from the prose):
{params}

Work through the physics and compute every requested quantity numerically.

Respond with ONLY the final numeric answer(s), one per line, in exactly
this form:

ANSWER <name>: <value> <unit>

For example:
ANSWER net_work: 300.75 kJ
ANSWER cycle_efficiency: 0.583

Do not show your working, do not restate the problem, do not include any
text before or after the ANSWER lines.
