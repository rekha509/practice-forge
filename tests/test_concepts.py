"""S5 idempotency plumbing tests. Fake LLM client + fake embeddings only —
no real API call, no accuracy claim (see tests/stubs.py's docstring for
why that distinction matters in this codebase)."""

from __future__ import annotations

import json
import re
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

import practice_forge.concepts.concepts as concepts_module
from practice_forge.concepts.concepts import run_concept_distillation
from practice_forge.db.models import (
    BookORM,
    ConceptCardORM,
    ConceptClusterORM,
    DisciplineORM,
    SectionORM,
    SourceProblemORM,
)
from practice_forge.llm.client import LLMResponse
from practice_forge.models.enums import ProblemKind


class _FakeDistillationClient:
    """One canned item per candidate in the prompt. The generated equation/
    dims/method depend only on the item's position WITHIN this call, not
    on any real problem identity — two separate calls that each distill a
    single problem at position 0 will therefore produce identical
    fingerprints, which is exactly the cross-run scenario the clustering
    fix needs to be checked against."""

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
                "name": f"concept-{i}",
                "governing_equations_latex": [f"E_{i} = m_{i} * c^2"],
                "assumptions": [],
                "solution_strategy": "solve",
                "typical_pitfalls": [],
                "given_dimensions": ["mass"],
                "solve_for_dimension": "energy",
                "method_tag": f"method-{i}",
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


def _fake_embed_texts(
    api_key: str, texts: list[str], rate_limiter: object | None = None
) -> list[list[float]]:
    return [[0.0] * 3072 for _ in texts]


def _make_book(session: Session) -> uuid.UUID:
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
    return book.id


def _add_problem(session: Session, book_id: uuid.UUID, statement: str) -> SourceProblemORM:
    section = session.execute(
        select(SectionORM).where(SectionORM.book_id == book_id)
    ).scalars().first()
    assert section is not None
    problem = SourceProblemORM(
        id=uuid.uuid4(),
        book_id=book_id,
        section_id=section.id,
        page_no=1,
        kind=ProblemKind.WORKED_EXAMPLE,
        statement_md=statement,
        is_solvable=True,
    )
    session.add(problem)
    session.flush()
    return problem


def test_distillation_is_idempotent_on_rerun(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(concepts_module, "embed_texts", _fake_embed_texts)
    book_id = _make_book(db_session)
    _add_problem(db_session, book_id, "Problem A")
    _add_problem(db_session, book_id, "Problem B")
    _add_problem(db_session, book_id, "Problem C")

    fake_client = _FakeDistillationClient()
    result_1 = run_concept_distillation(db_session, book_id, job_id="t1", llm_client=fake_client)
    assert result_1["distilled"] == 3
    calls_after_first_run = fake_client.call_count

    cards_after_first = (
        db_session.execute(select(ConceptCardORM).where(ConceptCardORM.book_id == book_id))
        .scalars()
        .all()
    )
    clusters_after_first = db_session.execute(select(ConceptClusterORM)).scalars().all()
    assert len(cards_after_first) == 3

    result_2 = run_concept_distillation(db_session, book_id, job_id="t2", llm_client=fake_client)
    assert result_2 == {"distilled": 0, "parse_failures": 0, "clusters": 0}
    # No new problems to distill -> the early-return path never reaches the
    # client at all. Re-running must not re-spend LLM quota.
    assert fake_client.call_count == calls_after_first_run

    cards_after_second = (
        db_session.execute(select(ConceptCardORM).where(ConceptCardORM.book_id == book_id))
        .scalars()
        .all()
    )
    clusters_after_second = db_session.execute(select(ConceptClusterORM)).scalars().all()
    assert len(cards_after_second) == len(cards_after_first)
    assert len(clusters_after_second) == len(clusters_after_first)
    assert {c.id for c in cards_after_second} == {c.id for c in cards_after_first}


def test_new_problem_merges_into_existing_cluster_across_runs(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clustering fix this test guards: without it, a second S5 run's
    new card would only be compared against other cards from THAT run, not
    against clusters persisted by an earlier run — a genuine duplicate
    concept introduced later would wrongly get its own new cluster instead
    of merging, which is exactly the no-repeat guarantee breaking silently.
    """
    monkeypatch.setattr(concepts_module, "embed_texts", _fake_embed_texts)
    book_id = _make_book(db_session)
    fake_client = _FakeDistillationClient()

    _add_problem(db_session, book_id, "Problem A")
    run_concept_distillation(db_session, book_id, job_id="run1", llm_client=fake_client)

    _add_problem(db_session, book_id, "Problem B")
    run_concept_distillation(db_session, book_id, job_id="run2", llm_client=fake_client)

    cards = (
        db_session.execute(select(ConceptCardORM).where(ConceptCardORM.book_id == book_id))
        .scalars()
        .all()
    )
    clusters = db_session.execute(select(ConceptClusterORM)).scalars().all()
    assert len(cards) == 2
    # Both calls distill a single problem at local index 0 -> identical
    # fingerprint -> must collapse into ONE cluster, not two.
    assert len(clusters) == 1
    assert set(clusters[0].member_card_ids) == {c.id for c in cards}
