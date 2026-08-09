"""S2 unit tests: chapter/section boundary detection and topic matching —
pure functions, no DB needed."""

from __future__ import annotations

import uuid

from practice_forge.db.models import TopicNodeORM
from practice_forge.structure.structure import detect_sections, match_topic_nodes


def test_detect_sections_splits_on_chapter_headings() -> None:
    pages = [
        (1, "Title: Strength of Materials"),
        (2, "Chapter 4: Bending Stress in Beams"),
        (3, "Some theory paragraph about bending."),
        (4, "Example 4.3: A beam problem."),
        (5, "Chapter 5: Shear Force and Torsion"),
        (6, "Some theory paragraph about shear."),
    ]
    sections = detect_sections(pages)

    assert len(sections) == 3
    assert sections[0].chapter_no is None
    assert sections[0].title == "Front Matter"
    assert sections[0].page_start == 1
    assert sections[0].page_end == 1
    assert sections[1].chapter_no == 4
    assert sections[1].title == "Bending Stress in Beams"
    assert sections[1].page_start == 2
    assert sections[1].page_end == 4
    assert sections[2].chapter_no == 5
    assert sections[2].page_start == 5
    assert sections[2].page_end == 6


def test_detect_sections_falls_back_to_untitled_when_no_headings() -> None:
    pages = [(1, "Just some prose, no chapter markers.")]
    sections = detect_sections(pages)
    assert len(sections) == 1
    assert sections[0].chapter_no is None
    assert sections[0].title == "Untitled"


def test_detect_sections_empty_book() -> None:
    assert detect_sections([]) == []


def test_match_topic_nodes_finds_overlap_via_name() -> None:
    surveying = TopicNodeORM(id=uuid.uuid4(), name="Surveying", aliases=[])
    thermo = TopicNodeORM(id=uuid.uuid4(), name="Thermodynamics", aliases=[])

    result = match_topic_nodes("Chain Surveying Methods", [surveying, thermo])
    assert result == [surveying.id]


def test_match_topic_nodes_finds_overlap_via_alias() -> None:
    som = TopicNodeORM(id=uuid.uuid4(), name="Strength of Materials", aliases=["bending", "torsion"])
    result = match_topic_nodes("Bending Stress in Beams", [som])
    assert result == [som.id]


def test_match_topic_nodes_returns_empty_when_no_overlap() -> None:
    som = TopicNodeORM(id=uuid.uuid4(), name="Strength of Materials", aliases=[])
    result = match_topic_nodes("Bending Stress in Beams", [som])
    assert result == []


def test_match_topic_nodes_empty_candidates() -> None:
    assert match_topic_nodes("Anything", []) == []
