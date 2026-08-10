"""Real embeddings via `gemini-embedding-001` — not BGE-M3, see
docs/adr/0008. A thin, swappable wrapper: if BGE-M3 (or any other model)
is ever stood up, this one function is the integration point."""

from __future__ import annotations

from google import genai

from practice_forge.llm.rate_limiter import RateLimiter
from practice_forge.llm.routing import load_routing

EMBEDDING_MODEL = "gemini-embedding-001"
_PROVIDER = "gemini"

# Confirmed live: the API rejects a batch over this size with
# "BatchEmbedContentsRequest.requests: at most 100 requests can be in one
# batch" (400 INVALID_ARGUMENT). A full 700-page book is projected at
# ~117 solvable concepts, over this cap in one call — chunking is
# required, not defensive margin.
MAX_BATCH_SIZE = 100


def embed_texts(
    api_key: str, texts: list[str], rate_limiter: RateLimiter | None = None
) -> list[list[float]]:
    """Not routed through `llm/client.py::LLMClient` — embedding isn't a
    `generate_content`-style call, so there's no per-stage route for it,
    just a direct (provider, model) rate-limit lookup. Still goes through
    the SAME `RateLimiter`/persistent-state mechanism `LLMClient` uses
    (see config/llm_routing.yaml's `gemini-embedding-001` entry): daily
    quota state is read/written to a shared JSON file keyed by
    provider:model:date, not held in memory, so a fresh `RateLimiter()`
    here correctly observes/shares counts with every other caller —
    embedding calls were previously invisible to rate limiting entirely, a
    real gap now closed. `DailyQuotaExhausted` propagates uncaught, same
    as every other real call in this codebase — no retry into a wall."""
    if not texts:
        return []
    limiter = rate_limiter or RateLimiter()
    limits = load_routing().limits_for(_PROVIDER, EMBEDDING_MODEL)

    client = genai.Client(api_key=api_key)
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        chunk = texts[i : i + MAX_BATCH_SIZE]
        limiter.acquire(_PROVIDER, EMBEDDING_MODEL, limits)
        response = client.models.embed_content(model=EMBEDDING_MODEL, contents=chunk)  # type: ignore[arg-type]
        if response.embeddings is None:
            raise RuntimeError("gemini-embedding-001 returned no embeddings")
        embeddings.extend(list(e.values or []) for e in response.embeddings)
    return embeddings
