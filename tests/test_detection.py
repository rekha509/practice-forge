"""Phase 3 detection tests.

`test_detection_precision_and_recall_against_labelled_spans` is the REAL
P3 gate: it makes a real batched call to whatever `config/llm_routing.yaml`
routes stage "s3_confirm" to (Gemini free tier as of docs/adr/0006) and
reports actual precision/recall — no stub, no stand-in. It's marked
`@pytest.mark.llm` per the project's testing standard (deselect with
`pytest -m "not llm"`) since it costs a real API call/request-quota unit
every time it runs.

The other tests below check plumbing (persistence, section-linking,
figure_dependency default) using `stub_batch_confirm_fn` from
`tests/stubs.py`, explicitly opted into per-test via `PF_USE_STUB_LLM=1` —
see that module's docstring and PROGRESS.md's Phase 3 correction for why
this distinction is enforced rather than just documented.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import SourceProblemORM
from practice_forge.detection.detection import make_default_batch_confirm_fn
from practice_forge.detection.detection import run_detection as run_detection_
from practice_forge.ingest.pipeline import run_ingest
from practice_forge.models.enums import ProblemKind
from practice_forge.structure.structure import run_structure
from tests.stubs import stub_batch_confirm_fn

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.mark.llm
def test_detection_precision_and_recall_against_labelled_spans(db_session: Session) -> None:
    """The real gate: no stub. Reports actual precision/recall from a live
    call to the routed s3_confirm model, untuned against this fixture."""
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

    confirm_fn = make_default_batch_confirm_fn(job_id="test-p3-gate")
    run_detection_(db_session, ingest_result.book_id, confirm_fn=confirm_fn)

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

    print(f"\nP3 GATE (real LLM, untuned): precision={precision:.3f} recall={recall:.3f}")
    print(f"  detected pages: {sorted(detected_pages)}")
    print(f"  ground truth positives: {sorted(ground_truth_positive_pages)}")
    print(f"  false positives (detected but not real): {sorted(false_positives)}")
    print(f"  false negatives (missed real problems): {sorted(false_negatives)}")

    assert detected_pages <= all_pages, "detected a page not covered by the labelled fixture"
    assert precision >= 0.80, f"precision {precision} (FP pages: {false_positives})"
    assert recall >= 0.80, f"recall {recall} (missed pages: {false_negatives})"


def test_regex_false_positive_is_rejected_by_confirm_pass(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PF_USE_STUB_LLM", "1")

    ingest_result = run_ingest(
        db_session,
        FIXTURES / "detection_sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    run_structure(db_session, ingest_result.book_id)
    run_detection_(db_session, ingest_result.book_id, confirm_fn=stub_batch_confirm_fn)

    page_4_problems = db_session.execute(
        select(SourceProblemORM).where(
            SourceProblemORM.book_id == ingest_result.book_id,
            SourceProblemORM.page_no == 4,
        )
    ).scalars().all()
    assert page_4_problems == []


def test_confirmed_problems_carry_kind_and_given_find(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PF_USE_STUB_LLM", "1")

    ingest_result = run_ingest(
        db_session,
        FIXTURES / "detection_sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    run_structure(db_session, ingest_result.book_id)
    run_detection_(db_session, ingest_result.book_id, confirm_fn=stub_batch_confirm_fn)

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


def test_stub_confirm_fn_raises_loudly_without_opt_in() -> None:
    with pytest.raises(RuntimeError, match="PF_USE_STUB_LLM"):
        stub_batch_confirm_fn(["Example 1.1: some text"])
