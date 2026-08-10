"""S6 idempotency plumbing test. Fake LLM client only — no real API call,
no accuracy claim (see tests/stubs.py's docstring for why that distinction
matters in this codebase)."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import (
    BookORM,
    CandidateScoreORM,
    ConceptCardORM,
    DisciplineORM,
    SectionORM,
    SourceProblemORM,
)
from practice_forge.models.enums import ProblemKind
from practice_forge.llm.client import LLMResponse
from practice_forge.scoring.scoring import run_scoring


class _FakeScoringClient:
    def __init__(self) -> None:
        self.call_count = 0

    def complete(
        self,
        *,
        stage: str,
        prompt: str,
        job_id: str,
        system: str | None = None,
        max_tokens: int = 2048,
        output_schema: dict[str, object] | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        n = len(re.findall(r"\[index \d+\]", prompt))
        items = [
            {
                "index": i,
                "pedagogical_value": 0.5,
                "computational_suitability": 0.5,
                "self_containedness": 0.5,
                "syllabus_centrality": 0.5,
                "verifiability": 0.5,
                "ml_extension_potential": 0.5,
                "difficulty": "medium",
                "scoring_rationale": {"pedagogical_value": "fake"},
            }
            for i in range(n)
        ]
        return LLMResponse(
            text=json.dumps(items),
            stop_reason="stop",
            provider="fake",
            model="fake",
            input_tokens=0,
            output_tokens=0,
            extra_tokens=0,
            cost_usd=0.0,
        )


def _make_book_with_cards(session: Session, n: int) -> uuid.UUID:
    discipline = session.execute(
        select(DisciplineORM).where(DisciplineORM.key == "mechanical")
    ).scalar_one()
    book = BookORM(
        id=uuid.uuid4(),
        title="Test Book",
        authors=[],
        discipline_id=discipline.id,
        page_count=10,
        file_sha256=uuid.uuid4().hex,
        uploaded_by="test",
    )
    session.add(book)
    session.flush()
    section = SectionORM(
        id=uuid.uuid4(), book_id=book.id, chapter_no=1, title="Ch1", page_start=1, page_end=10
    )
    session.add(section)
    session.flush()

    for i in range(n):
        problem = SourceProblemORM(
            id=uuid.uuid4(),
            book_id=book.id,
            section_id=section.id,
            page_no=1,
            kind=ProblemKind.WORKED_EXAMPLE,
            statement_md=f"Problem {i}",
            is_solvable=True,
        )
        session.add(problem)
        session.flush()
        session.add(
            ConceptCardORM(
                id=uuid.uuid4(),
                book_id=book.id,
                section_id=section.id,
                source_problem_id=problem.id,
                name=f"concept-{i}",
                governing_equations_latex=[f"E_{i} = m_{i} * c^2"],
                canonical_equation_srepr=[f"UNPARSED::E_{i} = m_{i} * c^2"],
                solution_strategy="solve",
                given_dimensions=["mass"],
                solve_for_dimension="energy",
                method_tag=f"method-{i}",
                concept_fingerprint=f"fingerprint-{i}",
                embedding=[0.0] * 3072,
                source_pages=[1],
            )
        )
    session.flush()
    return book.id


def test_scoring_is_idempotent_on_rerun(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    book_id = _make_book_with_cards(db_session, 3)
    fake_client = _FakeScoringClient()

    result_1 = run_scoring(db_session, book_id, job_id="t1", llm_client=fake_client)
    assert result_1 == {"scored": 3, "candidates": 3}
    calls_after_first_run = fake_client.call_count

    scores_after_first = db_session.execute(select(CandidateScoreORM)).scalars().all()
    assert len(scores_after_first) == 3

    result_2 = run_scoring(db_session, book_id, job_id="t2", llm_client=fake_client)
    assert result_2 == {"scored": 0, "candidates": 3}
    # No unscored cards left -> the early-return path never reaches the
    # client at all. Re-running must not re-spend LLM quota.
    assert fake_client.call_count == calls_after_first_run

    scores_after_second = db_session.execute(select(CandidateScoreORM)).scalars().all()
    assert len(scores_after_second) == len(scores_after_first)
    assert {s.id for s in scores_after_second} == {s.id for s in scores_after_first}
