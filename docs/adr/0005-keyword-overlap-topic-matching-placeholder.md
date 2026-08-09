# 5. Section→TopicNode matching is a keyword-overlap placeholder

## Status
Accepted

## Context
S2 requires mapping detected `Section`s onto `TopicNode`s. A real chapter
title ("Bending Stress in Beams") and a broad syllabus topic name ("Strength
of Materials") routinely share zero literal words — Jaccard-style keyword
overlap between them is 0 even when the mapping is obviously correct to a
human. Getting this genuinely right needs either a curated `aliases[]` list
per `TopicNode` (the field already exists in the schema for exactly this)
or an LLM classification pass.

## Decision
`structure/structure.py`'s `match_topic_nodes` is a keyword-overlap
heuristic over each `TopicNode`'s `name` **and** `aliases`. It is correct
and testable on titles that genuinely share vocabulary with a topic name or
one of its aliases, and is expected to return no match (empty
`topic_node_ids`) on titles that don't — which, for now, is most real
chapter titles, since no `TopicNode.aliases` have been populated yet.

## Consequences
- `run_structure` will assign few or no topics on a real textbook until
  someone curates `aliases[]` per topic (e.g. "Strength of Materials"
  gaining aliases like "bending", "torsion", "beam deflection") or this is
  replaced with an LLM pass over chapter title + a sample of its content.
- Not blocking Phase 3's gate (`pytest tests/test_detection.py`), which
  tests problem *detection* precision/recall, not topic-mapping accuracy.
  `tests/test_structure.py` tests `match_topic_nodes` directly against
  constructed cases with and without vocabulary overlap, not against real
  textbook chapter titles.
- Revisit when Phase 6 (candidate scoring/selection) needs topic spread as
  a real selection constraint — inaccurate topic assignment would directly
  undermine the ">= 6 distinct TopicNodes" hard constraint in S7.
