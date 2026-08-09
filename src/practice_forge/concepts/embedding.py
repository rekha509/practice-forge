"""Real embeddings via `gemini-embedding-001` — not BGE-M3, see
docs/adr/0008. A thin, swappable wrapper: if BGE-M3 (or any other model)
is ever stood up, this one function is the integration point."""

from __future__ import annotations

from google import genai

EMBEDDING_MODEL = "gemini-embedding-001"


def embed_texts(api_key: str, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = genai.Client(api_key=api_key)
    response = client.models.embed_content(model=EMBEDDING_MODEL, contents=texts)  # type: ignore[arg-type]
    if response.embeddings is None:
        raise RuntimeError("gemini-embedding-001 returned no embeddings")
    return [list(e.values or []) for e in response.embeddings]
