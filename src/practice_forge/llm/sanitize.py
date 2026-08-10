"""Postgres text/varchar columns reject a literal NUL (0x00) byte outright
("PostgreSQL text fields cannot contain NUL bytes") — found live on the
full 781-page book: not in OCR'd page text (checked — none of the 781
persisted pages contain one), but in an LLM-generated field (S3's
`given`/`find`/`final_answer`), which rolled back an entire already-
confirmed batch's insert, discarding real LLM work that had already been
paid for in quota. Every pipeline stage that persists LLM-generated
strings needs this, not just the one that happened to trip over it first.
"""

from __future__ import annotations


def strip_nul(text: str) -> str:
    return text.replace("\x00", "")


def strip_nul_opt(text: str | None) -> str | None:
    return None if text is None else strip_nul(text)


def strip_nul_list(texts: list[str]) -> list[str]:
    return [strip_nul(t) for t in texts]
