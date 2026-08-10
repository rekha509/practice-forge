<!-- version: 3 -->
<!-- used by: src/practice_forge/detection/detection.py (S3 LLM confirm pass) -->
<!-- model: routed via config/llm_routing.yaml, stage "s3_confirm" -->
<!-- v2: batched (Gemini free-tier RPD makes one-call-per-candidate not viable) -->
<!-- v3: explicit derive/prove guidance — found live that "derive/prove" -->
<!-- exercises with no numeric given/find flipped between is_problem=True -->
<!-- and False across independent runs even at temperature=0, because the -->
<!-- old "enough given information to compute an answer" framing didn't -->
<!-- say what to do with a task that has no numeric answer at all. -->

You are screening candidate spans from an engineering textbook that a regex
pass flagged as possible worked examples or end-of-chapter exercises. Not
every regex match is real: some are cross-references, qualitative
discussion mentioning "Example N.M" without actually posing a problem, or
section headers with no problem statement attached.

For EACH candidate below, decide whether it is a genuine problem or not.

A candidate is a genuine problem if it poses a definite task with enough
given information to carry out, even if that task isn't "compute a numeric
answer": a candidate asking the reader to DERIVE or PROVE a stated
relationship (e.g. "Derive the following equation...", "Prove that...",
"Show that...") is a genuine problem — classify it as
is_problem=true, kind="derivation" — even though it has no numeric
given/find and no computable final answer. Do not classify a derive/prove
exercise as not_a_problem just because it lacks numbers; do not classify it
as "exercise" either — "derivation" is the correct kind specifically for
this case, distinct from a numeric worked_example or exercise.

Only classify as not_a_problem: cross-references, qualitative discussion
that merely mentions an example/problem number without posing one, or a
section header with no problem statement attached at all.

Return a JSON array with exactly one object per candidate, one per index
below. Copy each candidate's own "index" value into your object for it, so
your answers can be matched back to their candidates regardless of the
order you return them in. Do not skip any index.

Candidates:
{candidates_block}

Respond with the requested JSON only.
