"""Phase 3 gate: precision and recall of S3 problem detection (regex
candidates + LLM confirm pass) against tests/fixtures/labelled_spans.json,
both required >= 0.80. The confirm pass is faked here per the testing
standard (never let a unit test hit the API) — it exercises the exact
decision `detection.py`'s real LLM confirm pass has to make: reject a
regex false-positive (page 4 matches "Example N.M" but isn't solvable),
accept the two genuine problems.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import SourceProblemORM
from practice_forge.detection.detection import ConfirmResult
from practice_forge.detection.detection import run_detection as run_detection_
from practice_forge.ingest.pipeline import run_ingest
from practice_forge.models.enums import ProblemKind
from practice_forge.structure.structure import run_structure

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fake_confirm(text: str) -> ConfirmResult:
    if "qualitatively only" in text:
        return ConfirmResult(is_problem=False, kind=None)
    if text.startswith("Problem"):
        return ConfirmResult(
            is_problem=True,
            kind=ProblemKind.EXERCISE,
            given=["T = 3 kN*m", "outer diameter = 60 mm", "inner diameter = 40 mm"],
            find=["shear stress at the outer surface"],
        )
    return ConfirmResult(
        is_problem=True,
        kind=ProblemKind.WORKED_EXAMPLE,
        given=["T = 2 kN*m", "diameter = 50 mm"],
        find=["tau_max"],
    )


def test_detection_precision_and_recall_against_labelled_spans(db_session: Session) -> None:
    labelled = json.loads((FIXTURES / "labelled_spans.json").read_text(encoding="utf-8"))
    ground_truth_positive_pages = {
        span["page_no"] for span in labelled["spans"] if span["is_problem"]
    }
    all_pages = {span["page_no"] for span in labelled["spans"]}

    ingest_result = run_ingest(
        db_session,
        FIXTURES / labelled["book_fixture"],
        discipline_key=labelled["discipline"],
        uploaded_by="test",
    )
    run_structure(db_session, ingest_result.book_id)
    run_detection_(db_session, ingest_result.book_id, confirm_fn=_fake_confirm)

    detected_pages = set(
        db_session.execute(
            select(SourceProblemORM.page_no).where(SourceProblemORM.book_id == ingest_result.book_id)
        )
        .scalars()
        .all()
    )

    true_positives = detected_pages & ground_truth_positive_pages
    false_positives = detected_pages - ground_truth_positive_pages
    false_negatives = ground_truth_positive_pages - detected_pages

    precision = len(true_positives) / len(detected_pages) if detected_pages else 0.0
    recall = (
        len(true_positives) / len(ground_truth_positive_pages)
        if ground_truth_positive_pages
        else 1.0
    )

    assert detected_pages <= all_pages, "detected a page not covered by the labelled fixture"
    assert precision >= 0.80, f"precision {precision} (FP pages: {false_positives})"
    assert recall >= 0.80, f"recall {recall} (missed pages: {false_negatives})"

    # This fixture is small and clean enough that the pipeline should hit
    # both exactly, not just clear the 0.80 bar.
    assert precision == 1.0
    assert recall == 1.0


def test_regex_false_positive_is_rejected_by_confirm_pass(db_session: Session) -> None:
    ingest_result = run_ingest(
        db_session,
        FIXTURES / "detection_sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    run_structure(db_session, ingest_result.book_id)
    run_detection_(db_session, ingest_result.book_id, confirm_fn=_fake_confirm)

    page_4_problems = db_session.execute(
        select(SourceProblemORM).where(
            SourceProblemORM.book_id == ingest_result.book_id,
            SourceProblemORM.page_no == 4,
        )
    ).scalars().all()
    assert page_4_problems == []


def test_confirmed_problems_carry_kind_and_given_find(db_session: Session) -> None:
    ingest_result = run_ingest(
        db_session,
        FIXTURES / "detection_sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    run_structure(db_session, ingest_result.book_id)
    run_detection_(db_session, ingest_result.book_id, confirm_fn=_fake_confirm)

    exercise = db_session.execute(
        select(SourceProblemORM).where(
            SourceProblemORM.book_id == ingest_result.book_id,
            SourceProblemORM.page_no == 6,
        )
    ).scalar_one()
    assert exercise.kind == ProblemKind.EXERCISE
    assert exercise.given
    assert exercise.find
    assert exercise.figure_dependency.value == "none"
