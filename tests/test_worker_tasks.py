"""Tests for worker/tasks.py's ledger-writing step (`_write_ledger`).

Real incident this responds to: the only real problem set in the dev DB
had exactly 1 issued ledger row, which looked like `_write_ledger` was
dropping rows for larger sets. Investigated live: that job's own
`JobORM.params` showed `count: 1` — it genuinely only ever requested (and
generated) one variant, so 1 ledger row was correct for that job, not a
bug. This test exercises `_write_ledger` directly against a REAL
multi-variant, multi-cluster problem set (three, not one) to prove it
writes one row per variant for real rather than relying on inference from
that single count=1 historical row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import IssuedLedgerORM, ProblemSetORM
from tests.test_api import _add_extra_cluster, _make_book_with_cluster, _make_course, _make_variant
from worker.tasks import _write_ledger


def test_write_ledger_writes_one_row_per_variant_in_the_set(db_session: Session) -> None:
    course = _make_course(db_session, faculty=None)
    book_id, section_id, cluster_1 = _make_book_with_cluster(db_session)
    cluster_2 = _add_extra_cluster(db_session, book_id, section_id)
    cluster_3 = _add_extra_cluster(db_session, book_id, section_id)

    variants = [_make_variant(db_session, c) for c in (cluster_1, cluster_2, cluster_3)]
    problem_set = ProblemSetORM(
        id=uuid.uuid4(),
        course_id=course.id,
        title="Test Set",
        run_number=1,
        variant_ids=[v.id for v in variants],
        typst_source="#set page()",
        student_pdf_path="/tmp/handout.pdf",
        solutions_pdf_path="/tmp/solutions.pdf",
        created_at=datetime.now(UTC),
    )
    db_session.add(problem_set)
    db_session.commit()

    _write_ledger(db_session, course_id=course.id, problem_set=problem_set)

    rows = (
        db_session.execute(
            select(IssuedLedgerORM).where(IssuedLedgerORM.problem_set_id == problem_set.id)
        )
        .scalars()
        .all()
    )
    assert len(rows) == len(variants) == 3
    assert {r.concept_cluster_id for r in rows} == {cluster_1, cluster_2, cluster_3}
    assert {r.variant_id for r in rows} == {v.id for v in variants}
    assert all(r.is_recycled is False for r in rows)


def test_write_ledger_denormalizes_is_recycled_from_the_variant(db_session: Session) -> None:
    """`is_recycled` is denormalized from Variant.is_recycled at write time
    (see IssuedLedgerORM's own docstring) -- a recycled variant must land
    with is_recycled=True on its ledger row too, or the partial unique
    index (course_id, concept_cluster_id) WHERE is_recycled=false stops
    meaning what it says."""
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    variant.is_recycled = True
    db_session.commit()

    problem_set = ProblemSetORM(
        id=uuid.uuid4(),
        course_id=course.id,
        title="Test Set",
        run_number=1,
        variant_ids=[variant.id],
        typst_source="#set page()",
        student_pdf_path="/tmp/handout.pdf",
        solutions_pdf_path="/tmp/solutions.pdf",
        created_at=datetime.now(UTC),
    )
    db_session.add(problem_set)
    db_session.commit()

    _write_ledger(db_session, course_id=course.id, problem_set=problem_set)

    row = db_session.execute(
        select(IssuedLedgerORM).where(IssuedLedgerORM.problem_set_id == problem_set.id)
    ).scalar_one()
    assert row.is_recycled is True
