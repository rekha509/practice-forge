<!-- version: 2 -->
<!-- used by: src/practice_forge/detection/detection.py (S3 LLM confirm pass) -->
<!-- model: routed via config/llm_routing.yaml, stage "s3_confirm" -->
<!-- v2: batched (Gemini free-tier RPD makes one-call-per-candidate not viable) -->

You are screening candidate spans from an engineering textbook that a regex
pass flagged as possible worked examples or end-of-chapter exercises. Not
every regex match is real: some are cross-references, qualitative
discussion mentioning "Example N.M" without actually posing a problem, or
section headers with no problem statement attached.

For EACH candidate below, decide whether it is a genuine, solvable problem
— one with enough given information to actually compute an answer — or not.

Return a JSON array with exactly one object per candidate, one per index
below. Copy each candidate's own "index" value into your object for it, so
your answers can be matched back to their candidates regardless of the
order you return them in. Do not skip any index.

Candidates:
{candidates_block}

Respond with the requested JSON only.
