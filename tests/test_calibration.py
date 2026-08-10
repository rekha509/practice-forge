"""Calibration mode tests.

`_match_book_values_to_solver` is a pure function tested here for real —
no mocking, genuine assertions about its matching logic.

`run_calibration`'s own test is explicitly PLUMBING ONLY: it monkeypatches
`generate_and_verify_solution` to a fixed fake result, so it proves
candidate selection / bucketing / report tallying wire together correctly.
It is NOT evidence of real solver accuracy — that only comes from running
`pf calibrate` for real against the real sandbox and a real LLM (see
tests/stubs.py's docstring and the `feedback_dont_overclaim_selfauthored_
test_validity` project memory for why this distinction is enforced here).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import (
    BookORM,
    ConceptCardORM,
    DisciplineORM,
    SectionORM,
    SourceProblemORM,
    VariantORM,
)
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import ProblemKind, VerificationStatus
from practice_forge.verification import calibration as calibration_module
from practice_forge.verification.answer_parsing import ParsedValue
from practice_forge.verification.calibration import _match_book_values_to_solver, run_calibration


def test_match_single_value_within_tolerance() -> None:
    matched, details = _match_book_values_to_solver({"efficiency": 0.583}, [ParsedValue(0.583, "")], tol=0.01)
    assert matched
    assert "MATCH" in details[0]


def test_match_single_value_outside_tolerance() -> None:
    matched, details = _match_book_values_to_solver({"efficiency": 0.9}, [ParsedValue(0.583, "")], tol=0.01)
    assert not matched
    assert "MISMATCH" in details[0]


def test_match_converts_units_before_comparing() -> None:
    # Solver reports SI base units (J); book answer is in kJ.
    matched, _ = _match_book_values_to_solver({"net_work": 300750.0}, [ParsedValue(300.75, "kJ")], tol=0.01)
    assert matched


def test_match_picks_nearest_solver_result_not_dict_order() -> None:
    solver_results = {"far_off": 999.0, "close": 45.6}
    matched, details = _match_book_values_to_solver(solver_results, [ParsedValue(45.6, "")], tol=0.01)
    assert matched
    assert "solver.close" in details[0]


def test_match_multiple_book_values_each_consume_a_distinct_solver_result() -> None:
    solver_results = {"a": 1.0, "b": 2.0}
    matched, details = _match_book_values_to_solver(
        solver_results, [ParsedValue(1.0, ""), ParsedValue(2.0, "")], tol=0.01
    )
    assert matched
    assert len(details) == 2


def test_match_reports_unmatched_when_fewer_solver_results_than_book_values() -> None:
    matched, details = _match_book_values_to_solver({"a": 1.0}, [ParsedValue(1.0, ""), ParsedValue(2.0, "")], tol=0.01)
    assert not matched
    assert any("no solver result left" in d for d in details)


def test_match_unrecognized_unit_is_flagged_not_silently_trusted() -> None:
    _, details = _match_book_values_to_solver({"x": 5.0}, [ParsedValue(5.0, "furlongs")], tol=0.01)
    assert "unit_recognized=False" in details[0]


def _make_book_with_problems(session: Session, answers: list[str | None]) -> uuid.UUID:
    discipline = session.execute(select(DisciplineORM).where(DisciplineORM.key == "mechanical")).scalar_one()
    book = BookORM(
        id=uuid.uuid4(),
        title="Calibration Test Book",
        authors=[],
        discipline_id=discipline.id,
        page_count=10,
        file_sha256=uuid.uuid4().hex,
        uploaded_by="test",
    )
    session.add(book)
    session.flush()
    section = SectionORM(id=uuid.uuid4(), book_id=book.id, chapter_no=1, title="Ch1", page_start=1, page_end=10)
    session.add(section)
    session.flush()

    for i, answer in enumerate(answers):
        problem = SourceProblemORM(
            id=uuid.uuid4(),
            book_id=book.id,
            section_id=section.id,
            page_no=i + 1,
            kind=ProblemKind.WORKED_EXAMPLE,
            statement_md=f"Problem {i}",
            final_answer=answer,
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


def test_run_calibration_plumbing(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """PLUMBING ONLY (see module docstring): fakes the solver entirely, so
    this proves candidate selection / bucketing / tallying, not accuracy."""
    book_id = _make_book_with_problems(
        db_session,
        [
            "45.6 kJ/kg",  # will "match" the faked solver result below
            "Flow is from right to left",  # unparseable, must be bucketed as such
            None,  # no final_answer at all, must be excluded from candidates entirely
        ],
    )

    def _fake_generate_and_verify_solution(
        client: object,
        job_id: str,
        card: ConceptCardORM,
        variant: VariantORM,
        *,
        extra_libs: list[str],
        sandbox_image: str,
        sandbox_timeout_s: int,
    ) -> None:
        variant.verification_status = VerificationStatus.VERIFIED
        variant.verified_answer = "{'answer': 45600.0}"  # SI base (J/kg) for 45.6 kJ/kg
        variant.verification_log = ["fake"]

    monkeypatch.setattr(calibration_module, "generate_and_verify_solution", _fake_generate_and_verify_solution)

    report = run_calibration(
        db_session,
        book_id,
        client=LLMClient.__new__(LLMClient),  # never actually called — generate_and_verify_solution is faked
        limit=10,
        sandbox_image="unused:latest",
        extra_libs=[],
    )

    # Only the 2 rows with a non-null final_answer are candidates at all.
    assert report.total_candidates == 2
    assert report.matched == 1
    assert report.mismatched == 0
    assert report.unparseable_book_answer == 1
    assert report.solver_failed == 0
    assert {row.outcome for row in report.rows} == {"matched", "unparseable_book_answer"}
