"""S10: Typst rendering — student handout PDF, faculty solutions manual
PDF, and a code/ folder with each problem's runnable Python.

Free-text fields (statement_md, solution_steps, names) come from real LLM
output and can contain characters Typst's own markup syntax treats
specially (`$` for math mode, `_`/`*` for emphasis, `#` for code, etc.) —
escaped via `_typst_escape` before being embedded, so a problem statement
that happens to contain a literal `$` or `_` doesn't break the document
or silently trigger Typst's math/emphasis parsing on LaTeX-flavoured text
it was never meant to interpret. This means inline LaTeX math in these
fields renders as literal escaped text, not real typeset math — a
disclosed simplification for this session (full LaTeX->Typst math
conversion is a real, separate piece of work, not attempted here), not a
silent gap.

Ledger-commit / ProblemSet persistence (writing an IssuedLedger row so
the no-repeat guarantee actually advances) is NOT done by this module —
that needs a real Course to exist, which nothing in this CLI-driven flow
has created yet. Disclosed here, not silently skipped: `run_render`
produces real PDFs on disk from the real, already-verified pool, but
"issuing" them against a course's ledger is separate follow-up work.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import typst
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import ConceptCardORM, VariantORM
from practice_forge.models.enums import VerificationStatus
from practice_forge.selection.selection import run_selection

_TYPST_SPECIAL = re.compile(r"([\\#*_$\[\]<>@`])")


def _typst_escape(text: str) -> str:
    return _TYPST_SPECIAL.sub(r"\\\1", text)


@dataclass(frozen=True)
class RenderedProblem:
    index: int
    card: ConceptCardORM
    variant: VariantORM


@dataclass(frozen=True)
class RenderResult:
    student_pdf_path: str
    solutions_pdf_path: str
    code_dir: str
    problem_count: int


def _collect_rendered_problems(session: Session, book_id: uuid.UUID) -> list[RenderedProblem]:
    """Re-runs the real S7 selection and pairs each selected concept with
    its own already-verified Variant (S8/S9). A selected concept with no
    verified variant yet (still pending, or generation/verification never
    ran for it) is skipped, not padded — the render only ever includes
    real, execution-verified problems."""
    selection_result = run_selection(session, book_id)
    problems: list[RenderedProblem] = []
    for i, member in enumerate(selection_result.selected):
        variant = (
            session.execute(
                select(VariantORM)
                .where(
                    VariantORM.concept_cluster_id == member.cluster_id,
                    VariantORM.verification_status == VerificationStatus.VERIFIED,
                )
                .order_by(VariantORM.id.desc())
            )
            .scalars()
            .first()
        )
        if variant is None:
            continue
        problems.append(RenderedProblem(index=len(problems) + 1, card=member.card, variant=variant))
    return problems


def _student_handout_typst(problems: list[RenderedProblem], title: str) -> str:
    lines = [
        "#set page(margin: 1in)",
        '#set text(font: "New Computer Modern", size: 11pt)',
        f'#align(center)[#text(size: 18pt, weight: "bold")[{_typst_escape(title)}]]',
        "#align(center)[Student Practice Set]",
        "#v(1em)",
    ]
    for p in problems:
        lines.append(f"== Problem {p.index}")
        lines.append(_typst_escape(p.variant.statement_md))
    return "\n\n".join(lines)


def _solutions_manual_typst(problems: list[RenderedProblem], title: str) -> str:
    lines = [
        "#set page(margin: 1in)",
        '#set text(font: "New Computer Modern", size: 11pt)',
        f'#align(center)[#text(size: 18pt, weight: "bold")[{_typst_escape(title)}]]',
        "#align(center)[Faculty Solutions Manual --- execution-verified]",
        "#v(1em)",
    ]
    for p in problems:
        lines.append(f"== Problem {p.index}: {_typst_escape(p.card.name)}")
        lines.append(_typst_escape(p.variant.statement_md))
        lines.append("*Solution approach:*")
        for step in p.variant.solution_steps:
            lines.append(f"+ {_typst_escape(step)}")
        lines.append(
            "*Verified answer* (computed by actually executing the accompanying code "
            "in a sandbox, not asserted by a model):"
        )
        lines.append(f"```\n{p.variant.verified_answer}\n```")
        lines.append(f"Code: `code/problem_{p.index:02d}.py`")
    return "\n\n".join(lines)


def run_render(session: Session, book_id: uuid.UUID, out_dir: Path, title: str) -> RenderResult:
    problems = _collect_rendered_problems(session, book_id)
    if not problems:
        raise ValueError("no verified problems to render for this book yet")

    out_dir.mkdir(parents=True, exist_ok=True)
    code_dir = out_dir / "code"
    code_dir.mkdir(exist_ok=True)

    for p in problems:
        (code_dir / f"problem_{p.index:02d}.py").write_text(
            p.variant.core_python_code, encoding="utf-8"
        )

    handout_typ = out_dir / "student_handout.typ"
    handout_pdf = out_dir / "student_handout.pdf"
    handout_typ.write_text(_student_handout_typst(problems, title), encoding="utf-8")
    typst.compile(str(handout_typ), output=str(handout_pdf))

    solutions_typ = out_dir / "solutions_manual.typ"
    solutions_pdf = out_dir / "solutions_manual.pdf"
    solutions_typ.write_text(_solutions_manual_typst(problems, title), encoding="utf-8")
    typst.compile(str(solutions_typ), output=str(solutions_pdf))

    return RenderResult(
        student_pdf_path=str(handout_pdf),
        solutions_pdf_path=str(solutions_pdf),
        code_dir=str(code_dir),
        problem_count=len(problems),
    )
