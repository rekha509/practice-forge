"""Calibration mode: the strongest accuracy check available, ahead of the
blind re-solve (see blind_resolve.py) because it checks against the book's
OWN printed answer, not another model's guess.

For each SourceProblem with a non-null `final_answer`, this builds a
transient (never persisted) Variant whose `statement_md` is the ORIGINAL
problem text, UNCHANGED — no S8 LLM call, no new numbers. S9's real
codegen + sandbox execution (`generate_and_verify_solution`) then solves it
exactly as it would a real generated variant. Any mismatch is therefore
attributable to the solver (bad code, wrong physics, wrong units), not to
a rewritten problem — that's the whole point of holding the parameters
fixed.

The book's `final_answer` is real, messy, OCR'd free text (see
answer_parsing.py for the parser this depends on) — some fraction of rows
are not numeric at all (qualitative answers) or are symbolic formulas, and
those are honestly reported as `unparseable_book_answer`, not silently
skipped from the denominator.
"""

from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.codegen.codegen import generate_and_verify_solution
from practice_forge.db.models import ConceptCardORM, SourceProblemORM, VariantORM
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus
from practice_forge.verification.answer_parsing import (
    ComparisonResult,
    ParsedValue,
    compare_values,
    parse_numeric_values,
)


@dataclass(frozen=True)
class CalibrationRow:
    source_problem_id: uuid.UUID
    page_no: int
    book_answer_raw: str
    solver_results: dict[str, float] | None
    outcome: str  # "matched" | "mismatched" | "unparseable_book_answer" | "solver_failed"
    detail: str


@dataclass(frozen=True)
class CalibrationReport:
    total_candidates: int
    matched: int
    mismatched: int
    unparseable_book_answer: int
    solver_failed: int
    rows: list[CalibrationRow] = field(default_factory=list)


def _match_book_values_to_solver(
    solver_results: dict[str, float], book_values: list[ParsedValue], tol: float
) -> tuple[bool, list[str]]:
    """Greedy nearest-match, each solver result usable at most once: for
    each book value (in order), pick the unused solver result with the
    smallest relative difference and accept it if within `tol`. Returns
    (all_book_values_matched, per-value detail strings) — a deliberately
    simple heuristic, not a rigorous optimal assignment, because S9's
    prompt doesn't guarantee a printed RESULT name lines up with the
    book's own answer's position or label."""
    unused = dict(solver_results)
    all_matched = True
    details: list[str] = []
    for bv in book_values:
        best_name: str | None = None
        best_result: ComparisonResult | None = None
        for name, si_value in unused.items():
            result = compare_values(si_value, bv.value, bv.unit, tol=tol)
            is_better = best_result is None or (
                result.relative_difference is not None
                and (
                    best_result.relative_difference is None
                    or result.relative_difference < best_result.relative_difference
                )
            )
            if is_better:
                best_name, best_result = name, result
        if best_name is None or best_result is None:
            all_matched = False
            details.append(f"book={bv.value}{bv.unit} -> no solver result left to compare")
            continue
        rel_str = f"{best_result.relative_difference:.4f}" if best_result.relative_difference is not None else "n/a"
        details.append(
            f"book={bv.value}{bv.unit} vs solver.{best_name}={unused[best_name]:.6g} "
            f"(SI) rel_diff={rel_str} unit_recognized={best_result.unit_recognized} "
            f"-> {'MATCH' if best_result.matched else 'MISMATCH'}"
        )
        if not best_result.matched:
            all_matched = False
        del unused[best_name]
    return all_matched, details


def run_calibration(
    session: Session,
    book_id: uuid.UUID,
    client: LLMClient,
    *,
    limit: int,
    sandbox_image: str,
    extra_libs: list[str],
    sandbox_timeout_s: int = 15,
    tol: float = 0.01,
) -> CalibrationReport:
    """Selects up to `limit` SourceProblem rows (joined to their real
    ConceptCard) with a non-null, at-least-one-value-parseable
    `final_answer`, solves each with unchanged parameters, and compares.
    Nothing here is persisted — calibration variants never hit the DB."""
    candidates = session.execute(
        select(SourceProblemORM, ConceptCardORM)
        .join(ConceptCardORM, ConceptCardORM.source_problem_id == SourceProblemORM.id)
        .where(SourceProblemORM.book_id == book_id, SourceProblemORM.final_answer.isnot(None))
        .order_by(SourceProblemORM.page_no)
        .limit(limit)
    ).all()

    rows: list[CalibrationRow] = []
    matched = mismatched = unparseable = solver_failed = 0

    for i, (problem, card) in enumerate(candidates):
        assert problem.final_answer is not None
        book_values = parse_numeric_values(problem.final_answer)
        if book_values is None:
            unparseable += 1
            rows.append(
                CalibrationRow(
                    source_problem_id=problem.id,
                    page_no=problem.page_no,
                    book_answer_raw=problem.final_answer,
                    solver_results=None,
                    outcome="unparseable_book_answer",
                    detail="no numeric value found in final_answer",
                )
            )
            continue

        variant = VariantORM(
            id=uuid.uuid4(),
            concept_cluster_id=uuid.uuid4(),  # placeholder — this variant is never persisted
            statement_md=problem.statement_md,
            params={},
            difficulty=DifficultyLevel.MEDIUM,
            topic_node_ids=[],
            solution_steps=[],
            core_python_code="",
            extension_type=ExtensionType.NONE,
            extension_python_code=None,
            extension_learning_notes=None,
            extension_figure_paths=[],
            extension_metrics_json=None,
            verified_answer=None,
            verification_status=VerificationStatus.PENDING,
            verification_log=[],
            needs_review=False,
            source_ref={
                "source_problem_id": str(problem.id),
                "book_id": str(book_id),
                "page_no": problem.page_no,
                "mode": "calibration",
            },
            is_recycled=False,
        )

        generate_and_verify_solution(
            client,
            f"calibrate-{book_id}-{i}",
            card,
            variant,
            extra_libs=extra_libs,
            sandbox_image=sandbox_image,
            sandbox_timeout_s=sandbox_timeout_s,
        )

        if variant.verification_status != VerificationStatus.VERIFIED or variant.verified_answer is None:
            solver_failed += 1
            rows.append(
                CalibrationRow(
                    source_problem_id=problem.id,
                    page_no=problem.page_no,
                    book_answer_raw=problem.final_answer,
                    solver_results=None,
                    outcome="solver_failed",
                    detail="; ".join(variant.verification_log[-2:]),
                )
            )
            continue

        try:
            solver_results = ast.literal_eval(variant.verified_answer)
        except (ValueError, SyntaxError):
            solver_failed += 1
            rows.append(
                CalibrationRow(
                    source_problem_id=problem.id,
                    page_no=problem.page_no,
                    book_answer_raw=problem.final_answer,
                    solver_results=None,
                    outcome="solver_failed",
                    detail=f"verified_answer did not parse as a dict: {variant.verified_answer!r}",
                )
            )
            continue

        all_matched, details = _match_book_values_to_solver(solver_results, book_values, tol)
        if all_matched:
            matched += 1
        else:
            mismatched += 1
        rows.append(
            CalibrationRow(
                source_problem_id=problem.id,
                page_no=problem.page_no,
                book_answer_raw=problem.final_answer,
                solver_results=solver_results,
                outcome="matched" if all_matched else "mismatched",
                detail="; ".join(details),
            )
        )

    return CalibrationReport(
        total_candidates=len(candidates),
        matched=matched,
        mismatched=mismatched,
        unparseable_book_answer=unparseable,
        solver_failed=solver_failed,
        rows=rows,
    )
