"""S2: chapter/section boundaries. TOC-driven (structure/toc.py) is the
PRIMARY path, per the spec's original design — a real LLM pass over the
table of contents, then real fuzzy text matching to locate each chapter's
actual page. Heading regex (`detect_sections` below) is the FALLBACK, used
only when no TOC can be found/parsed or nothing gets located from it — not
tuning the regex to fit one book, replacing it as the primary strategy.

Section -> TopicNode mapping unchanged from the original design (keyword
overlap, docs/adr/0005). Discipline classification is NOT implemented here
— the uploader already supplies `--discipline` at ingest (S1).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, PageORM, SectionORM, TopicNodeORM
from practice_forge.llm.client import LLMClient
from practice_forge.structure.toc import (
    LocatedChapter,
    find_toc_text,
    locate_chapter_pages,
    parse_toc,
)

_CHAPTER_PATTERN = re.compile(r"^\s*Chapter\s+(\d+)\s*:?\s*(.*)$", re.IGNORECASE)

TOPIC_MATCH_THRESHOLD = 0.15


@dataclass(frozen=True)
class DetectedSection:
    chapter_no: int | None
    title: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class StructureRunReport:
    method: str  # "toc" or "regex_fallback"
    toc_entries_parsed: int
    chapters_located: int


def detect_sections(pages: list[tuple[int, str]]) -> list[DetectedSection]:
    """FALLBACK ONLY (see module docstring). `pages`: (page_no, markdown) in
    page order. A page's first non-blank line matching `Chapter N[: title]`
    starts a new section running to the page before the next chapter
    heading (or end of book)."""
    headings: list[tuple[int, int | None, str]] = []
    for page_no, text in pages:
        stripped = text.strip()
        if not stripped:
            continue
        first_line = stripped.splitlines()[0]
        match = _CHAPTER_PATTERN.match(first_line)
        if match:
            title = match.group(2).strip() or first_line
            headings.append((page_no, int(match.group(1)), title))

    if not pages:
        return []

    if not headings:
        return [DetectedSection(None, "Untitled", pages[0][0], pages[-1][0])]

    sections = []
    first_page_no = pages[0][0]
    last_page_no = pages[-1][0]

    if headings[0][0] > first_page_no:
        sections.append(DetectedSection(None, "Front Matter", first_page_no, headings[0][0] - 1))

    for i, (page_no, chapter_no, title) in enumerate(headings):
        page_end = headings[i + 1][0] - 1 if i + 1 < len(headings) else last_page_no
        sections.append(DetectedSection(chapter_no, title, page_no, page_end))
    return sections


def detect_sections_from_located_chapters(
    located: list[LocatedChapter], pages: list[tuple[int, str]]
) -> list[DetectedSection]:
    """Same span-building logic as `detect_sections`, but from real
    TOC-parsed + fuzzy-matched chapter starts instead of regex matches."""
    if not pages:
        return []
    first_page_no = pages[0][0]
    last_page_no = pages[-1][0]

    sections: list[DetectedSection] = []
    if located and located[0].page_no > first_page_no:
        sections.append(
            DetectedSection(None, "Front Matter", first_page_no, located[0].page_no - 1)
        )
    for i, chapter in enumerate(located):
        page_end = located[i + 1].page_no - 1 if i + 1 < len(located) else last_page_no
        sections.append(DetectedSection(chapter.chapter_no, chapter.title, chapter.page_no, page_end))
    return sections


def _keyword_overlap(a: str, b: str) -> float:
    words_a = set(re.findall(r"[a-z]+", a.lower()))
    words_b = set(re.findall(r"[a-z]+", b.lower()))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def match_topic_nodes(
    section_title: str,
    topic_nodes: list[TopicNodeORM],
    threshold: float = TOPIC_MATCH_THRESHOLD,
) -> list[uuid.UUID]:
    """Keyword-overlap heuristic against each TopicNode's name and aliases.
    Deliberately simple — see docs/adr/0005 for why, and what to replace it
    with once accuracy matters more than "doesn't crash"."""
    best_node: TopicNodeORM | None = None
    best_score = 0.0
    for node in topic_nodes:
        candidates = [node.name, *node.aliases]
        score = max(_keyword_overlap(section_title, candidate) for candidate in candidates)
        if score > best_score:
            best_score = score
            best_node = node
    if best_node is None or best_score < threshold:
        return []
    return [best_node.id]


def run_structure(
    session: Session, book_id: uuid.UUID, llm_client: LLMClient | None = None
) -> tuple[list[SectionORM], StructureRunReport]:
    book = session.get(BookORM, book_id)
    if book is None:
        raise ValueError(f"No such book: {book_id}")

    pages = (
        session.execute(
            select(PageORM.page_no, PageORM.markdown)
            .where(PageORM.book_id == book_id)
            .order_by(PageORM.page_no)
        )
        .all()
    )
    pages_tuples = [(p.page_no, p.markdown) for p in pages]

    toc_text = find_toc_text(pages_tuples)
    if toc_text is not None:
        client = llm_client or LLMClient()
        entries = parse_toc(client, job_id=f"structure-toc-{book_id}", toc_text=toc_text)
        located = locate_chapter_pages(entries, pages_tuples)
        if located:
            detected = detect_sections_from_located_chapters(located, pages_tuples)
            report = StructureRunReport("toc", len(entries), len(located))
        else:
            detected = detect_sections(pages_tuples)
            report = StructureRunReport("regex_fallback", len(entries), 0)
    else:
        detected = detect_sections(pages_tuples)
        report = StructureRunReport("regex_fallback", 0, 0)

    topic_nodes = (
        session.execute(select(TopicNodeORM).where(TopicNodeORM.discipline_id == book.discipline_id))
        .scalars()
        .all()
    )

    sections: list[SectionORM] = []
    for d in detected:
        section = SectionORM(
            id=uuid.uuid4(),
            book_id=book_id,
            chapter_no=d.chapter_no,
            title=d.title,
            page_start=d.page_start,
            page_end=d.page_end,
            topic_node_ids=match_topic_nodes(d.title, list(topic_nodes)),
        )
        session.add(section)
        sections.append(section)
    session.flush()
    return sections, report
