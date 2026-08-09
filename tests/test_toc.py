"""S2 TOC-driven detection unit tests: pure functions, no LLM call (the
real LLM call in `parse_toc` isn't exercised here — see test_structure.py's
pattern of testing the surrounding logic directly)."""

from __future__ import annotations

from practice_forge.structure.structure import detect_sections_from_located_chapters
from practice_forge.structure.toc import (
    LocatedChapter,
    TocEntry,
    find_toc_text,
    locate_chapter_pages,
)


def test_find_toc_text_locates_contents_block() -> None:
    pages = [
        (1, "Some title page"),
        (2, "Contents\n1. Intro 1\n2. Temperature 24\n3. Work 37"),
        (3, "4. First Law 63\n5. Flow Processes 81\n6. Second Law 111"),
        (4, "Not TOC shaped text at all, just prose with no numbers ending lines"),
        (5, "Chapter 1\nActual body content starts here"),
    ]
    toc_text = find_toc_text(pages)
    assert toc_text is not None
    assert "Contents" in toc_text
    assert "First Law" in toc_text
    # Page 4 doesn't look TOC-shaped, so collection should have stopped by then.
    assert "Not TOC shaped" not in toc_text


def test_find_toc_text_returns_none_when_no_contents_page() -> None:
    pages = [(1, "Just prose."), (2, "More prose.")]
    assert find_toc_text(pages) is None


def test_locate_chapter_pages_finds_real_heading_despite_ocr_noise() -> None:
    entries = [
        TocEntry(chapter_no=5, title="First Law Applied to Flow Processes", printed_page=81),
        TocEntry(chapter_no=6, title="Second Law of Thermodynamics", printed_page=111),
    ]
    pages = [
        (86, "First Law Applied to\nFlow Processes\n5.1 Control Volume"),
        (90, "some body text about steady flow"),
        (116, "Second Law of\nThermodynamics\n6.1 Qualitative Difference"),
    ]
    located = locate_chapter_pages(entries, pages)
    assert [c.chapter_no for c in located] == [5, 6]
    assert located[0].page_no == 86
    assert located[1].page_no == 116


def test_locate_chapter_pages_skips_entries_with_no_content_in_range() -> None:
    entries = [
        TocEntry(chapter_no=1, title="Introduction", printed_page=1),
        TocEntry(chapter_no=5, title="First Law Applied to Flow Processes", printed_page=81),
    ]
    pages = [(86, "First Law Applied to\nFlow Processes\n5.1 Control Volume")]
    located = locate_chapter_pages(entries, pages)
    assert [c.chapter_no for c in located] == [5]


def test_detect_sections_from_located_chapters_builds_spans() -> None:
    located = [
        LocatedChapter(chapter_no=5, title="First Law Applied to Flow Processes", page_no=86),
        LocatedChapter(chapter_no=6, title="Second Law of Thermodynamics", page_no=116),
    ]
    pages = [(p, "") for p in range(80, 120)]
    sections = detect_sections_from_located_chapters(located, pages)
    assert sections[0].title == "Front Matter"
    assert sections[0].page_start == 80
    assert sections[0].page_end == 85
    assert sections[1].chapter_no == 5
    assert sections[1].page_start == 86
    assert sections[1].page_end == 115
    assert sections[2].chapter_no == 6
    assert sections[2].page_start == 116
    assert sections[2].page_end == 119
