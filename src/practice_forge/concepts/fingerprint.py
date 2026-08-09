"""Concept fingerprinting: LaTeX -> canonical SymPy srepr -> sha256. The
fingerprint is a pure function of physics identity (equations + given/solve
dimensions + method tag), never of wording, numbers, or source book — S1's
book-level dedup and S5/S7's concept-level dedup both depend on that
invariant holding.
"""

from __future__ import annotations

import hashlib
import logging

import sympy
from sympy.parsing.latex import parse_latex

logger = logging.getLogger("practice_forge.concepts")


def canonicalize_equation(latex: str) -> str:
    """Parses LaTeX into a SymPy expression and returns its `srepr` — the
    same physics in different symbol names/ordering hashes identically
    only if SymPy's own canonical form treats them as equal; this does NOT
    do symbol-name normalization beyond what SymPy's parser does. Real
    OCR/LLM-authored LaTeX sometimes fails to parse (verified live: this
    happens on real content, not hypothetical) — falls back to the
    stripped raw LaTeX string so a parse failure degrades to "novel
    fingerprint" rather than crashing the whole distillation batch.
    """
    try:
        expr = parse_latex(latex)
        return str(sympy.srepr(expr))
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        logger.warning("canonicalize_equation: parse_latex failed for %r: %s", latex, exc)
        return f"UNPARSED::{latex.strip()}"


def concept_fingerprint(
    canonical_equation_srepr: list[str],
    given_dimensions: list[str],
    solve_for_dimension: str,
    method_tag: str,
) -> str:
    parts = [
        "|".join(sorted(canonical_equation_srepr)),
        "|".join(sorted(given_dimensions)),
        solve_for_dimension.strip().lower(),
        method_tag.strip().lower(),
    ]
    digest_input = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(digest_input).hexdigest()
