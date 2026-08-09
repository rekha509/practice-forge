"""TOC-driven chapter detection (S2), per the spec's original design ("an
LLM pass over the TOC") rather than heading regex alone. Regex
(`structure.detect_sections`) is now the FALLBACK, used only when no table
of contents can be found/parsed, or when it yields nothing usable — not
the primary path.

Three real steps, no fabrication:
1. Find the TOC block in the ingested pages (heuristic: starts at a page
   containing "Contents", extends while later pages still look TOC-shaped).
2. One real LLM call parses that block into a chapter list with the book's
   OWN printed page numbers (not PDF indices — this book's OCR pagination
   doesn't map to PDF indices by any constant offset, confirmed on
   tests/fixtures/nag_real.pdf).
3. Real fuzzy text matching (stdlib `difflib`, tolerant of OCR noise)
   locates each parsed chapter's actual PDF page index by searching for
   its title in the ingested pages' real content — never assumed from the
   TOC's own page numbers arithmetically.

A book excerpt (not the whole book) will have most TOC entries unlocatable
— their content simply isn't in the ingested page range. That's reported
as "not found in this ingest," not a matching failure.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from practice_forge.llm.client import LLMClient

MATCH_SCORE_THRESHOLD = 0.55
MAX_TOC_PAGES = 12  # safety cap; real TOCs seen so far are ~5 pages

_TOC_START_PATTERN = re.compile(r"\bContents\b", re.IGNORECASE)
_TRAILING_PAGE_NUMBER = re.compile(r"\d{1,4}\s*$")

_TOC_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "s2_toc_parse.md"


class TocEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_no: int
    title: str
    printed_page: int


@dataclass(frozen=True)
class LocatedChapter:
    chapter_no: int
    title: str
    page_no: int  # real PDF page index this chapter was found to start at


def find_toc_text(pages: list[tuple[int, str]]) -> str | None:
    """Heuristic: find the first page containing "Contents", then keep
    including subsequent pages while they still look TOC-shaped (a good
    fraction of lines end in a page number) — real TOCs run a few pages;
    stop once that pattern drops off or the safety cap is hit."""
    start_idx = None
    for i, (_, text) in enumerate(pages):
        if _TOC_START_PATTERN.search(text):
            start_idx = i
            break
    if start_idx is None:
        return None

    collected: list[str] = [pages[start_idx][1]]
    for _, text in pages[start_idx + 1 : start_idx + 1 + MAX_TOC_PAGES]:
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            break
        toc_like_lines = sum(1 for line in lines if _TRAILING_PAGE_NUMBER.search(line))
        if toc_like_lines / len(lines) < 0.3:
            break
        collected.append(text)
    return "\n".join(collected)


def parse_toc(llm_client: LLMClient, job_id: str, toc_text: str) -> list[TocEntry]:
    prompt = _TOC_PROMPT_PATH.read_text(encoding="utf-8").replace("{toc_text}", toc_text)
    schema = {"type": "array", "items": TocEntry.model_json_schema()}
    response = llm_client.complete(
        stage="s2_structure",
        prompt=prompt,
        job_id=job_id,
        max_tokens=4096,
        output_schema=schema,
    )
    try:
        raw_items = json.loads(response.text)
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_items, list):
        return []

    entries: list[TocEntry] = []
    for raw in raw_items:
        try:
            entries.append(TocEntry.model_validate(raw))
        except ValidationError:
            continue  # one malformed TOC row doesn't invalidate the rest
    return entries


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def locate_chapter_pages(
    entries: list[TocEntry], pages: list[tuple[int, str]]
) -> list[LocatedChapter]:
    """For each TOC entry, search every page for a fuzzy match against its
    title, trying the page's first 1, 2, and 3 non-blank lines as candidate
    headings and keeping whichever window scores best FOR THAT PAGE.

    A single fixed window size fails on real content in both directions:
    a wide window (3 lines) dilutes the ratio on a chapter's true start
    page, where the title is immediately followed by body prose (e.g.
    "Work and Heat Transfer" + a full following sentence scored 0.23
    against its own title) — a later page's shorter, noisier running
    header then wins on ratio despite being the wrong page. A narrow
    window (1 line) instead breaks on titles that print wrapped across two
    lines (confirmed: "Second Law of" / "Thermodynamics" on separate
    lines) — the truncated "Second Law of" then loses to a same-family
    chapter's single-line title ("First Law of Thermodynamics" scores
    0.84 against it, beating the true match's truncated 0.63). Taking the
    best of 1/2/3-line windows per page fixes both: a clean, complete
    title (whether on one line or wrapped across two) reaches a 1.0 exact
    match at whichever window captures it fully, which beats every
    OCR-noisy or partial-title candidate found so far on this book.
    """
    located: list[LocatedChapter] = []
    for entry in entries:
        normalized_title = _normalize(entry.title)
        if not normalized_title:
            continue

        best_page_no: int | None = None
        best_score = 0.0
        for page_no, text in pages:
            lines = [line for line in text.splitlines() if line.strip()]
            page_best_score = 0.0
            for window in (1, 2, 3):
                head_text = _normalize(" ".join(lines[:window]))
                if not head_text:
                    continue
                score = difflib.SequenceMatcher(None, normalized_title, head_text).ratio()
                page_best_score = max(page_best_score, score)
            if page_best_score > best_score:
                best_score = page_best_score
                best_page_no = page_no

        if best_page_no is not None and best_score >= MATCH_SCORE_THRESHOLD:
            located.append(LocatedChapter(entry.chapter_no, entry.title, best_page_no))

    located.sort(key=lambda c: c.page_no)
    return located
