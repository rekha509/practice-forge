"""S7 selection: `_scale_difficulty_mix` is tested directly (pure
function); `run_selection`'s new `section_ids`/`target_set_size`/
`difficulty_mix` parameters are tested against a small hand-built DB pool
sized so the per-section-cap-scaling behavior is directly checkable by
counting the real selected members, not by parsing a constraint-report
string."""

from __future__ import annotations

import uuid
from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import (
    BookORM,
    CandidateScoreORM,
    ConceptCardORM,
    ConceptClusterORM,
    DisciplineORM,
    SectionORM,
    SourceProblemORM,
)
from practice_forge.models.enums import DifficultyLevel, ProblemKind
from practice_forge.selection.selection import (
    DIFFICULTY_TARGET,
    _scale_difficulty_mix,
    run_selection,
)


def test_scale_difficulty_mix_at_default_size_matches_literal_target() -> None:
    assert _scale_difficulty_mix(20) == DIFFICULTY_TARGET == {"easy": 6, "medium": 9, "hard": 5}


@pytest.mark.parametrize("size", [1, 4, 6, 7, 10, 13, 47])
def test_scale_difficulty_mix_always_sums_to_target_size(size: int) -> None:
    mix = _scale_difficulty_mix(size)
    assert sum(mix.values()) == size
    assert set(mix) == {"easy", "medium", "hard"}
    assert all(v >= 0 for v in mix.values())


def _make_book_with_sections(session: Session, cards_per_section: dict[str, int]) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    discipline = session.execute(
        select(DisciplineORM).where(DisciplineORM.key == "mechanical")
    ).scalar_one()
    book = BookORM(
        id=uuid.uuid4(),
        title="Selection Test Book",
        authors=[],
        discipline_id=discipline.id,
        page_count=10,
        file_sha256=uuid.uuid4().hex,
        uploaded_by="test",
    )
    session.add(book)
    session.flush()

    section_ids: dict[str, uuid.UUID] = {}
    card_index = 0
    for name, n in cards_per_section.items():
        section = SectionORM(
            id=uuid.uuid4(), book_id=book.id, chapter_no=1, title=name, page_start=1, page_end=10
        )
        session.add(section)
        session.flush()
        section_ids[name] = section.id

        for _ in range(n):
            card_index += 1
            embedding = [0.0] * 3072
            embedding[card_index] = 1.0  # mutually orthogonal -> cosine 0 across all cards
            problem = SourceProblemORM(
                id=uuid.uuid4(),
                book_id=book.id,
                section_id=section.id,
                page_no=1,
                kind=ProblemKind.WORKED_EXAMPLE,
                statement_md=f"Problem {card_index}",
                is_solvable=True,
            )
            session.add(problem)
            session.flush()
            card = ConceptCardORM(
                id=uuid.uuid4(),
                book_id=book.id,
                section_id=section.id,
                source_problem_id=problem.id,
                name=f"concept-{card_index}",
                topic_node_ids=[uuid.uuid4()],
                governing_equations_latex=[f"E_{card_index} = m c^2"],
                canonical_equation_srepr=[f"UNPARSED::E_{card_index}"],
                solution_strategy="solve",
                given_dimensions=["mass"],
                solve_for_dimension="energy",
                method_tag=f"method-{card_index}",
                concept_fingerprint=f"fp-{card_index}",
                embedding=embedding,
                source_pages=[1],
            )
            session.add(card)
            session.flush()
            session.add(
                CandidateScoreORM(
                    id=uuid.uuid4(),
                    concept_card_id=card.id,
                    pedagogical_value=0.5,
                    computational_suitability=5,
                    self_containedness=0.5,
                    syllabus_centrality=0.5,
                    verifiability=0.5,
                    ml_extension_potential=0.5,
                    difficulty=DifficultyLevel.MEDIUM,
                    eligible_extension_types=["surrogate_model"],
                    composite_score=0.5,
                    scoring_rationale={},
                )
            )
            session.add(
                ConceptClusterORM(
                    id=uuid.uuid4(),
                    discipline_id=discipline.id,
                    representative_card_id=card.id,
                    member_card_ids=[card.id],
                    centroid_embedding=embedding,
                )
            )
    session.flush()
    return book.id, section_ids


def test_section_ids_none_or_empty_means_whole_book(db_session: Session) -> None:
    book_id, _sections = _make_book_with_sections(db_session, {"A": 2, "B": 2})
    result_none = run_selection(db_session, book_id, target_set_size=3)
    assert result_none.pool_size == 4  # both sections visible by default

    result_empty = run_selection(db_session, book_id, section_ids=frozenset(), target_set_size=3)
    assert result_empty.pool_size == 4


def test_section_ids_filters_pool_and_scales_per_section_cap(db_session: Session) -> None:
    book_id, sections = _make_book_with_sections(db_session, {"A": 4, "B": 4, "C": 4})

    result = run_selection(
        db_session,
        book_id,
        section_ids=frozenset({sections["A"], sections["B"]}),
        target_set_size=6,
    )

    assert result.pool_size == 8  # section C's 4 cards excluded
    assert result.can_reach_target is True
    assert len(result.selected) == 6

    section_counts = Counter(m.card.section_id for m in result.selected)
    assert set(section_counts) <= {sections["A"], sections["B"]}
    # max(3, ceil(6/2)) == 3 per section, reached exactly since each real
    # section has 4 available cards (more than the cap).
    assert max(section_counts.values()) <= 3


def test_small_section_subset_reports_honest_pool_size_not_padded(db_session: Session) -> None:
    book_id, sections = _make_book_with_sections(db_session, {"A": 4, "B": 4})

    result = run_selection(
        db_session, book_id, section_ids=frozenset({sections["A"]}), target_set_size=6
    )

    assert result.pool_size == 4
    assert result.can_reach_target is False
    assert "cannot reach the 6-problem target" in result.reason
    # max(3, ceil(6/1)) == 6 per section — with only 4 real members in the
    # single selected section, the per-section cap constraint itself still
    # reports as satisfied (4 <= 6); it's the absolute pool size that's short.
    per_section_key = next(k for k in result.constraints_satisfied if k.startswith("<="))
    assert result.constraints_satisfied[per_section_key] is True


def test_difficulty_mix_override_must_sum_to_target_size(db_session: Session) -> None:
    with pytest.raises(ValueError, match="sums to"):
        run_selection(
            db_session,
            uuid.uuid4(),
            target_set_size=10,
            difficulty_mix={"easy": 5, "medium": 5, "hard": 5},
        )
