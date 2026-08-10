"""S10 render tests. Pure functions only — no DB, no LLM call, no real
sandbox. `_latex_to_typst_math`'s tests use real equation strings this
project's own S5/S6 LLM calls have actually produced this session (see
git history), not invented LaTeX, so a regression here reflects a real
rendering failure, not a hypothetical one."""

from __future__ import annotations

import uuid
from pathlib import Path

import typst

from practice_forge.db.models import ConceptCardORM, VariantORM
from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus
from practice_forge.render.render import (
    RenderedProblem,
    _latex_to_typst_math,
    _render_text_with_math,
    _solutions_manual_typst,
    _student_handout_typst,
    _typst_raw_block,
)

# Real LaTeX this project's own LLM calls have produced this session.
REAL_EQUATIONS = [
    r"\eta = 1 - \frac{1}{r_p^{(\gamma-1)/\gamma}}",
    r"COP = \frac{h_1 - h_4}{h_2 - h_1}",
    r"\Delta S_{gen} = \sum \dot{m}_e s_e - \sum \dot{m}_i s_i \ge 0",
    r"\frac{A}{A^*} = \frac{1}{M} \left[ \frac{2}{\gamma+1} \left( 1 + \frac{\gamma-1}{2} M^2 \right) \right]^{\frac{\gamma+1}{2(\gamma-1)}}",
    r"Q_{process} = \dot{m} (h_2 - h_3)",
    r"\Delta S = \int \frac{m c_p dT}{T} + \frac{m L}{T}",
    r"\eta_{II} = \frac{\dot{E}_{gain}}{\dot{E}_{in}}",
    r"T_2 = T_1 \cdot r_p^{(\gamma-1)/\gamma}",
    r"p v^\gamma = \text{constant}",
    r"NTU = \frac{U_0 A}{C_{min}}",
]


def _make_problem(index: int, name: str, code: str, equations: list[str] | None = None) -> RenderedProblem:
    card = ConceptCardORM(
        id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        section_id=uuid.uuid4(),
        source_problem_id=uuid.uuid4(),
        name=name,
        topic_node_ids=[],
        governing_equations_latex=equations or [],
        canonical_equation_srepr=[],
        assumptions=[],
        solution_strategy="",
        typical_pitfalls=[],
        given_dimensions=[],
        solve_for_dimension="",
        method_tag="",
        concept_fingerprint="fp",
        embedding=[0.0] * 3072,
        source_pages=[1],
    )
    variant = VariantORM(
        id=uuid.uuid4(),
        concept_cluster_id=uuid.uuid4(),
        statement_md=f"Statement for {name} with inline math $\\eta = 1 - \\frac{{1}}{{r}}$.",
        params={"x": 1.0},
        difficulty=DifficultyLevel.MEDIUM,
        topic_node_ids=[],
        solution_steps=["Step one.", "Step two with $COP = 4.0$."],
        core_python_code=code,
        extension_type=ExtensionType.NONE,
        extension_python_code=None,
        extension_learning_notes=None,
        extension_figure_paths=[],
        extension_metrics_json=None,
        verified_answer="{'x': 1.0}",
        verification_status=VerificationStatus.VERIFIED,
        verification_log=[],
        needs_review=False,
        source_ref={},
        is_recycled=False,
    )
    return RenderedProblem(index=index, card=card, variant=variant)


def test_solutions_manual_contains_nonempty_code_block_per_problem() -> None:
    problems = [
        _make_problem(1, "Concept A", "import numpy as np\nprint('RESULT a: 1.0')"),
        _make_problem(2, "Concept B", "import scipy\nprint('RESULT b: 2.0')"),
        _make_problem(3, "Concept C", "print('RESULT c: 3.0')"),
    ]
    typst_source = _solutions_manual_typst(problems, "Test Set")

    sections = typst_source.split("== Problem ")[1:]
    assert len(sections) == len(problems)
    for problem, section in zip(problems, sections, strict=True):
        assert "```python" in section, f"problem {problem.index} has no python code block"
        # The block must actually contain the real code, not be an empty fence.
        assert problem.variant.core_python_code.strip() in section


def test_solutions_manual_compiles_with_real_code_and_equations(tmp_path: Path) -> None:
    problems = [
        _make_problem(
            1,
            "Brayton cycle",
            "import numpy as np\nprint('RESULT net_work: 300.75')",
            equations=[REAL_EQUATIONS[0], REAL_EQUATIONS[3]],
        ),
        _make_problem(
            2,
            "Refrigeration COP",
            "print('RESULT cop: 3.97')",
            equations=[REAL_EQUATIONS[1]],
        ),
    ]
    typst_source = _solutions_manual_typst(problems, "Test Set")
    out_typ = tmp_path / "test.typ"
    out_pdf = tmp_path / "test.pdf"
    out_typ.write_text(typst_source, encoding="utf-8")
    typst.compile(str(out_typ), output=str(out_pdf))
    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 0


def test_student_handout_has_one_section_per_problem() -> None:
    problems = [_make_problem(i, f"Concept {i}", "print(1)") for i in range(1, 4)]
    typst_source = _student_handout_typst(problems, "Test Set")
    for p in problems:
        assert f"== Problem {p.index}" in typst_source
    # Student handout must never leak the solver code.
    assert "```python" not in typst_source


def test_latex_to_typst_math_compiles_for_real_equations(tmp_path: Path) -> None:
    lines = ["#set page(margin: 1in)"]
    for eq in REAL_EQUATIONS:
        lines.append(f"$ {_latex_to_typst_math(eq)} $")
    out_typ = tmp_path / "eqs.typ"
    out_pdf = tmp_path / "eqs.pdf"
    out_typ.write_text("\n".join(lines), encoding="utf-8")
    # Must not raise — this is the actual regression this test guards:
    # a bare multi-letter acronym like "COP" once raised Typst's own
    # "unknown variable" error because Typst (unlike LaTeX) treats an
    # unbroken multi-letter run in math mode as an identifier lookup, not
    # adjacent italic letters.
    typst.compile(str(out_typ), output=str(out_pdf))
    assert out_pdf.exists()


def test_render_text_with_math_preserves_literal_dollar_amounts() -> None:
    text = r"This costs $5 per unit, but $\gamma = 1.4$ is the real ratio."
    rendered = _render_text_with_math(text)
    # The unpaired literal $5 must stay escaped prose, not be swallowed
    # into a math span with the real equation.
    assert r"\$5 per unit" in rendered
    assert "$gamma = 1.4$" in rendered


def test_typst_raw_block_fence_longer_than_embedded_backticks() -> None:
    code = "print('```not a real fence```')"
    block = _typst_raw_block(code, "python")
    assert block.startswith("````python")
    assert code in block
