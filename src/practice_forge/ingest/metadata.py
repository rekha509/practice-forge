"""Title-page metadata extraction + normalisation (S1b).

Heuristic pattern match over the first pages' text. Real textbook title
pages are messier than this (publisher boilerplate, ISBN blocks, cover
illustrations) — an LLM pass over the first few pages would generalise
far better. Deferred: this heuristic is enough to prove the dedup-matching
logic (S1b) correctly and is cheap (no API cost) for every ingest, even
ones that turn out to be exact-hash dedup hits before metadata is ever
needed. See docs/adr/0004.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FIELD_PATTERNS = {
    "title": re.compile(r"^\s*title\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "authors": re.compile(r"^\s*author[s]?\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "edition": re.compile(r"^\s*edition\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
}


@dataclass(frozen=True)
class BookMetadata:
    title: str
    authors: list[str]
    edition: str | None


def extract_metadata(first_pages_text: str) -> BookMetadata:
    title_match = _FIELD_PATTERNS["title"].search(first_pages_text)
    authors_match = _FIELD_PATTERNS["authors"].search(first_pages_text)
    edition_match = _FIELD_PATTERNS["edition"].search(first_pages_text)

    title = title_match.group(1).strip() if title_match else "Unknown Title"
    authors = (
        [a.strip() for a in authors_match.group(1).split(",") if a.strip()]
        if authors_match
        else []
    )
    edition = edition_match.group(1).strip() if edition_match else None
    return BookMetadata(title=title, authors=authors, edition=edition)


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace — for equality
    comparisons only, never for display."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def metadata_matches(a: BookMetadata, b: BookMetadata) -> bool:
    if normalise(a.title) != normalise(b.title):
        return False
    a_authors = {normalise(x) for x in a.authors}
    b_authors = {normalise(x) for x in b.authors}
    return not (a_authors and b_authors and a_authors != b_authors)
