"""Real embeddings via `gemini-embedding-001` — not BGE-M3, see
docs/adr/0008. A thin, swappable wrapper: if BGE-M3 (or any other model)
is ever stood up, this one function is the integration point."""

from __future__ import annotations

from google import genai

EMBEDDING_MODEL = "gemini-embedding-001"

# Confirmed live: the API rejects a batch over this size with
# "BatchEmbedContentsRequest.requests: at most 100 requests can be in one
# batch" (400 INVALID_ARGUMENT). A full 700-page book is projected at
# ~117 solvable concepts, over this cap in one call — chunking is
# required, not defensive margin.
MAX_BATCH_SIZE = 100


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = genai.Client(api_key=api_key)
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        chunk = texts[i : i + MAX_BATCH_SIZE]
        response = client.models.embed_content(model=EMBEDDING_MODEL, contents=chunk)  # type: ignore[arg-type]
        if response.embeddings is None:
            raise RuntimeError("gemini-embedding-001 returned no embeddings")
        embeddings.extend(list(e.values or []) for e in response.embeddings)
    return embeddings
