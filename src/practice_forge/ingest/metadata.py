"""Title-page metadata extraction + normalisation (S1b).

`extract_metadata` is a heuristic pattern match over the first pages'
text — cheap (no API cost), enough to prove the dedup-matching logic
(S1b) correctly, and it runs for every ingest, even ones that turn out to
be exact-hash dedup hits before metadata is ever needed. Real scanned
title pages are messier than this (publisher boilerplate, ISBN blocks,
cover illustrations) — confirmed live: it returns "Unknown Title" for
every one of this project's real full-book ingests (`docs/adr/0004`
predicted exactly this).

`extract_metadata_llm` is the real fallback the ADR called for: one
Gemini call over the same sample text, used only when the free heuristic
comes back empty — so a well-formatted PDF (or a test fixture) never
spends real quota it doesn't need, and a real messy scan gets a real
answer instead of a permanent "Unknown Title".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from practice_forge.llm.client import LLMClient

_FIELD_PATTERNS = {
    "title": re.compile(r"^\s*title\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "authors": re.compile(r"^\s*author[s]?\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    "edition": re.compile(r"^\s*edition\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
}

_METADATA_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "s1_metadata_extraction.md"
)


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


class _LLMMetadataResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None
    authors: list[str]
    edition: str | None


def extract_metadata_llm(client: LLMClient, job_id: str, first_pages_text: str) -> BookMetadata:
    """One real Gemini call, structured output, over the same sample text
    `extract_metadata` already had. Never invents a value the model
    didn't actually find — `title=None`/`edition=None`/`authors=[]` all
    pass straight through as "genuinely not present" rather than being
    coerced into a plausible-looking guess. Falls back to "Unknown Title"
    at the same point the pure-regex path would, not earlier."""
    prompt = _METADATA_PROMPT_PATH.read_text(encoding="utf-8").replace(
        "{sample_text}", first_pages_text[:4000]
    )
    response = client.complete(
        stage="s1_metadata",
        prompt=prompt,
        job_id=job_id,
        max_tokens=512,
        output_schema=_LLMMetadataResult.model_json_schema(),
    )
    try:
        result = _LLMMetadataResult.model_validate(json.loads(response.text))
    except (json.JSONDecodeError, ValidationError):
        return BookMetadata(title="Unknown Title", authors=[], edition=None)

    return BookMetadata(
        title=(result.title or "").strip() or "Unknown Title",
        authors=[a.strip() for a in result.authors if a.strip()],
        edition=(result.edition or "").strip() or None,
    )


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
