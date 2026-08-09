<!-- version: 1 -->
<!-- used by: src/practice_forge/detection/detection.py (S3 LLM confirm pass) -->
<!-- model: Claude Haiku 4.5 -->

You are screening a candidate span from an engineering textbook that a
regex pass flagged as a possible worked example or end-of-chapter exercise.
Not every regex match is real: some are cross-references, qualitative
discussion mentioning "Example N.M" without actually posing a problem, or
section headers with no problem statement attached.

Decide whether this candidate is a genuine, solvable problem — one with
enough given information to actually compute an answer — or not.

Candidate text:
---
{candidate_text}
---

Respond with the requested JSON only.
