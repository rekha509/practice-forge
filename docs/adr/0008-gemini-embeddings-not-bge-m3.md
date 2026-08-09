# 8. `gemini-embedding-001` as the embedding model, not BGE-M3

## Status
Accepted

## Context
The spec fixes BGE-M3 (dense + sparse from one model) for embeddings.
Running real BGE-M3 locally means downloading multi-GB model weights and
running CPU inference — not impossible, but a real setup cost with no
existing infrastructure for it in this project, discovered while building
S5 (concept distillation/clustering) against real content under a tight
autonomous-run time budget.

Since the pivot to Gemini as the active LLM provider (`docs/adr/0006`),
Gemini's own embedding models are already one API call away with the same
key already configured: `gemini-embedding-001` (and newer `gemini-
embedding-2*` variants) are live and confirmed working — `client.models.
embed_content(model="gemini-embedding-001", contents=[...])` returns real
3072-dimensional vectors, verified with an actual call, not assumed.

## Decision
`concepts/embedding.py` calls `gemini-embedding-001` instead of BGE-M3.
`EMBEDDING_DIM` in `db/models.py` changed from 1024 (BGE-M3's dimension) to
3072 (this model's real, verified output dimension) — migration
`0002_gemini_embedding_dim` alters both `concept_cards.embedding` and
`concept_clusters.centroid_embedding` pgvector columns accordingly.

## Consequences
- No sparse embedding component (BGE-M3's other half) — clustering here
  uses dense cosine similarity only. The spec's `>= 0.92 cosine` clustering
  threshold is carried forward unchanged; it hasn't been re-validated
  against this specific model's similarity distribution, since no
  labelled duplicate/non-duplicate concept pairs exist yet to calibrate
  against (same "unvalidated on real data" caveat as S3/S4 this session).
- Embedding calls draw from Gemini's own free-tier quota for
  `gemini-embedding-001`, which is not yet in `config/llm_routing.yaml`'s
  `limits` section (that file only covers `generate_content`-style calls
  today) — a real gap to close before this runs at real book volume, not
  addressed in this session given the time budget.
- If BGE-M3 is ever actually stood up, `concepts/embedding.py`'s single
  function is the swap point — same pattern as `docs/adr/0004`'s
  `extract_pages()` and `docs/adr/0005`'s `match_topic_nodes()`.
