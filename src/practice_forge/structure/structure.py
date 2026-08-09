"""S2: chapter/section boundaries from heading patterns, Section -> TopicNode
mapping. Discipline classification is NOT implemented here — the uploader
already supplies `--discipline` at ingest (S1); title/TOC-based
auto-detection is a documented future refinement, not required by the spec
("confirmable/overridable by the uploader" already covers a manual value).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, PageORM, SectionORM, TopicNodeORM

_CHAPTER_PATTERN = re.compile(r"^\s*Chapter\s+(\d+)\s*:?\s*(.*)$", re.IGNORECASE)

TOPIC_MATCH_THRESHOLD = 0.15


@dataclass(frozen=True)
class DetectedSection:
    chapter_no: int | None
    title: str
    page_start: int
    page_end: int


def detect_sections(pages: list[tuple[int, str]]) -> list[DetectedSection]:
    """`pages`: (page_no, markdown) in page order. A page's first non-blank
    line matching `Chapter N[: title]` starts a new section running to the
    page before the next chapter heading (or end of book)."""
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

    # Front matter (title page, preface) before the first chapter heading —
    # every page must fall inside some Section, since SourceProblem.section_id
    # is a required FK.
    if headings[0][0] > first_page_no:
        sections.append(DetectedSection(None, "Front Matter", first_page_no, headings[0][0] - 1))

    for i, (page_no, chapter_no, title) in enumerate(headings):
        page_end = headings[i + 1][0] - 1 if i + 1 < len(headings) else last_page_no
        sections.append(DetectedSection(chapter_no, title, page_no, page_end))
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


def run_structure(session: Session, book_id: uuid.UUID) -> list[SectionORM]:
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
    detected = detect_sections([(p.page_no, p.markdown) for p in pages])

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
    return sections
