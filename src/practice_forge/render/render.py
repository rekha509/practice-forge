"""S10: Typst rendering — student handout PDF, faculty solutions manual
PDF, and a code/ folder with each problem's runnable Python.

Free-text fields (statement_md, solution_steps, names) come from real LLM
output. Prose is escaped for Typst's markup (`_typst_escape` — `$`, `_`,
`*`, `#` etc. are markup-special) EXCEPT inline LaTeX math spans
(`$...$`), which are instead converted to real Typst math mode
(`_latex_to_typst_math`) and rendered as actual typeset equations, not
escaped literal text. The converter handles the real LaTeX subset this
project's own LLM calls emit (`\\frac`, `\\dot`/`\\hat`/`\\sqrt`,
`_{...}`/`^{...}` grouping, `\\text{...}`, `\\left`/`\\right` sizing,
common Greek letters and operators) — it is not a general LaTeX parser;
an unrecognized `\\command` degrades to its bare name (backslash
stripped) rather than crashing the render or silently dropping content.

Each problem's real Part A solver code is embedded inline in the
solutions manual as a Typst raw code block (`lang: "python"`), in
addition to being written to its own `code/problem_NN.py` file — the
solutions manual is meant to be readable on its own, not just a pointer
to a separate folder.

Ledger-commit / ProblemSet persistence (writing an IssuedLedger row so
the no-repeat guarantee actually advances) is NOT done by this module —
that needs a real Course to exist. Disclosed here, not silently skipped.
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


def _typst_raw_block(code: str, lang: str) -> str:
    """A Typst raw/code block, fenced with enough backticks to contain any
    backtick run already present in `code` (Typst's own rule: a raw
    block's closing fence must be at least as long as its opening one, and
    a longer fence "escapes" shorter backtick runs inside — real generated
    Python is exceedingly unlikely to contain a literal ``` sequence, but
    this doesn't assume that, it checks)."""
    longest_run = 0
    current = 0
    for ch in code:
        if ch == "`":
            current += 1
            longest_run = max(longest_run, current)
        else:
            current = 0
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{lang}\n{code}\n{fence}"


def _read_group(s: str, i: int) -> tuple[str, int]:
    """s[i] must be '{'. Returns (content between the balanced braces,
    index just after the matching closing brace)."""
    depth = 1
    j = i + 1
    start = j
    while j < len(s) and depth > 0:
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
        j += 1
    return s[start : j - 1], j


_LATEX_SYMBOLS = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "Gamma": "Gamma",
    "delta": "delta", "Delta": "Delta", "epsilon": "epsilon",
    "varepsilon": "epsilon", "zeta": "zeta", "eta": "eta", "theta": "theta",
    "Theta": "Theta", "iota": "iota", "kappa": "kappa", "lambda": "lambda",
    "Lambda": "Lambda", "mu": "mu", "nu": "nu", "xi": "xi", "Xi": "Xi",
    "pi": "pi", "Pi": "Pi", "rho": "rho", "sigma": "sigma", "Sigma": "Sigma",
    "tau": "tau", "upsilon": "upsilon", "phi": "phi", "varphi": "phi",
    "Phi": "Phi", "chi": "chi", "psi": "psi", "Psi": "Psi", "omega": "omega",
    "Omega": "Omega",
    "infty": "infinity", "partial": "diff", "nabla": "nabla",
    "cdot": "dot.c", "times": "times", "div": "div", "pm": "plus.minus",
    "mp": "minus.plus",
    "ge": ">=", "geq": ">=", "le": "<=", "leq": "<=", "ne": "!=",
    "neq": "!=", "approx": "approx", "equiv": "equiv", "propto": "prop",
    "sim": "tilde.op",
    "ln": "ln", "log": "log", "exp": "exp", "sin": "sin", "cos": "cos",
    "tan": "tan", "lim": "lim", "min": "min", "max": "max",
    "sum": "sum", "int": "integral", "oint": "integral.cont",
    "prod": "product",
    "rightarrow": "->", "to": "->", "leftarrow": "<-",
    "Rightarrow": "==>", "implies": "==>", "leftrightarrow": "<->",
    "forall": "forall", "exists": "exists", "in": "in", "notin": "in.not",
    "%": "%", "ldots": "dots", "cdots": "dots",
}

# Commands taking exactly one {...} argument, recursively converted, then
# wrapped in the named Typst accent/function.
_UNARY_COMMANDS = {
    "dot": "dot", "ddot": "dot.double", "hat": "hat", "bar": "macron",
    "vec": "arrow", "tilde": "tilde", "sqrt": "sqrt", "overline": "overline",
    "underline": "underline", "mathrm": "upright", "mathbf": "bold",
    "boldsymbol": "bold",
}


# Bare multi-letter words Typst's math mode already recognizes as
# built-in operators/constants — safe to leave unquoted. Anything else
# multi-letter (e.g. a real acronym like "COP") gets quoted, see the
# `c.isalpha()` branch in _latex_to_typst_math below.
_TYPST_SAFE_BARE_WORDS = {
    "sin", "cos", "tan", "sinh", "cosh", "tanh", "ln", "log", "exp",
    "min", "max", "lim", "mod", "gcd", "arg", "det", "dim", "ker", "deg",
}


def _skip_to_brace(s: str, i: int) -> int:
    j = i
    while j < len(s) and s[j] not in "{ ":
        j += 1
    while j < len(s) and s[j] == " ":
        j += 1
    return j


def _latex_to_typst_math(s: str) -> str:
    """Converts LaTeX math into Typst math syntax. Real subset this
    project's LLM calls actually emit (see module docstring) — an
    unrecognized `\\command` falls back to its bare name (backslash
    stripped, which Typst renders as a plain identifier) rather than
    raising or dropping content, since a slightly-wrong-looking symbol is
    far better than a crashed render or missing equation."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            j = i + 1
            while j < n and s[j].isalpha():
                j += 1
            cmd = s[i + 1 : j]
            if not cmd:
                # bare "\" followed by punctuation (e.g. "\," "\;" spacing
                # commands, or a literal "\\" line break) — drop it.
                i = j + 1 if j < n else j
                continue
            if cmd == "frac":
                k = _skip_to_brace(s, j)
                if k < n and s[k] == "{":
                    a_raw, k2 = _read_group(s, k)
                    k3 = _skip_to_brace(s, k2)
                    if k3 < n and s[k3] == "{":
                        b_raw, k4 = _read_group(s, k3)
                        out.append(f"(({_latex_to_typst_math(a_raw)})/({_latex_to_typst_math(b_raw)}))")
                        i = k4
                        continue
                out.append(cmd)
                i = j
            elif cmd == "text":
                k = _skip_to_brace(s, j)
                if k < n and s[k] == "{":
                    txt, k2 = _read_group(s, k)
                    out.append(f'"{txt}"')
                    i = k2
                    continue
                out.append(cmd)
                i = j
            elif cmd in _UNARY_COMMANDS:
                k = _skip_to_brace(s, j)
                if k < n and s[k] == "{":
                    arg, k2 = _read_group(s, k)
                    out.append(f"{_UNARY_COMMANDS[cmd]}({_latex_to_typst_math(arg)})")
                    i = k2
                    continue
                out.append(cmd)
                i = j
            elif cmd in ("left", "right", "big", "Big", "bigg", "Bigg"):
                i = j  # sizing only — Typst auto-sizes brackets, just drop the command
            elif cmd in _LATEX_SYMBOLS:
                out.append(_LATEX_SYMBOLS[cmd])
                i = j
            else:
                out.append(cmd)  # unknown command: strip backslash, keep the bare name
                i = j
        elif c in "_^":
            out.append(c)
            i += 1
            if i < n and s[i] == "{":
                arg, i2 = _read_group(s, i)
                out.append(f"({_latex_to_typst_math(arg)})")
                i = i2
        elif c == "{":
            out.append("(")
            i += 1
        elif c == "}":
            out.append(")")
            i += 1
        elif c.isalpha():
            # Found live compiling real equations: Typst treats a bare
            # multi-letter run in math mode as a single identifier lookup
            # and raises `unknown variable` if it isn't one already in
            # scope — unlike LaTeX, which just italicizes adjacent single
            # letters with no lookup at all. A single letter is always a
            # safe implicit variable in Typst; a real acronym like "COP"
            # is not. Multi-letter runs not in the small safe set below
            # are quoted (upright literal text) so they render instead of
            # crashing the compile.
            j = i
            while j < n and s[j].isalpha():
                j += 1
            word = s[i:j]
            if len(word) == 1 or word in _TYPST_SAFE_BARE_WORDS:
                out.append(word)
            else:
                out.append(f'"{word}"')
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


# `(?!\d)` after the opening `$`: a dollar sign immediately followed by a
# digit is a real currency amount ("$5", "$1.99"), not a LaTeX math
# delimiter — found live testing against text mixing a literal price with
# real inline math ("costs $5 ... but $\gamma = 1.4$ is the ratio"),
# where the naive pattern paired the currency "$" with the next "$" and
# swallowed the prose between them as bogus "math". This book's real
# content has no currency amounts, but the heuristic costs nothing and
# removes a real, demonstrated failure mode.
_INLINE_MATH = re.compile(r"\$(?!\d)([^$]+)\$")


def _render_text_with_math(text: str) -> str:
    """Escapes prose for Typst markup, but converts $...$ LaTeX math
    spans into real Typst math mode instead of escaping them as literal
    text — see _latex_to_typst_math for the supported subset."""
    parts: list[str] = []
    last_end = 0
    for m in _INLINE_MATH.finditer(text):
        parts.append(_typst_escape(text[last_end : m.start()]))
        parts.append(f"${_latex_to_typst_math(m.group(1))}$")
        last_end = m.end()
    parts.append(_typst_escape(text[last_end:]))
    return "".join(parts)


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
    for member in selection_result.selected:
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
        lines.append(_render_text_with_math(p.variant.statement_md))
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
        lines.append(_render_text_with_math(p.variant.statement_md))
        if p.card.governing_equations_latex:
            lines.append("*Governing equation(s):*")
            for eq in p.card.governing_equations_latex:
                lines.append(f"$ {_latex_to_typst_math(eq)} $")
        lines.append("*Solution approach:*")
        for step in p.variant.solution_steps:
            lines.append(f"+ {_render_text_with_math(step)}")
        lines.append(
            "*Verified answer* (computed by actually executing the accompanying code "
            "in a sandbox, not asserted by a model):"
        )
        lines.append(f"```\n{p.variant.verified_answer}\n```")
        lines.append(f"*Part A solver* (`code/problem_{p.index:02d}.py`, executed to produce the answer above):")
        lines.append(_typst_raw_block(p.variant.core_python_code, "python"))
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
