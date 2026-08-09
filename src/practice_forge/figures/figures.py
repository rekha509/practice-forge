"""S4, descoped for v1 (see docs/adr/0007): DETECTS figure-dependent
problems and excludes them from selection. Does NOT interpret figures —
no vision calls, no crop, no `structured_spec_json`. The `Figure` table and
this module's interface are kept as the integration point for real
interpretation later; nothing downstream needs to change when that lands.

Classification is text-only, not `Page.has_figure`: this book is scanned,
so every page is one embedded raster image and `pypdf`'s image-detection
signal (`Page.has_figure`) is `True` on literally every page — checked
empirically on `tests/fixtures/nag_real.pdf`, not assumed. The only real
signal available without actual figure interpretation is whether the
problem's own text references a figure/diagram.

Deliberately conservative and binary (NONE or ESSENTIAL, never DECORATIVE):
per the spec's own principle — "never guess geometry" — any problem whose
text points at a figure is treated as figure-dependent. Distinguishing a
genuinely decorative figure from an essential one requires seeing the
figure, which this stage explicitly does not do; defaulting an ambiguous
case to DECORATIVE would risk keeping a problem that secretly needs
geometry from a diagram. Excluding a solvable-without-the-figure problem
is the safe direction to be wrong in.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import SourceProblemORM
from practice_forge.models.enums import FigureDependency

_FIGURE_REFERENCE_PATTERN = re.compile(
    r"\b("
    r"fig\.?\s*\d|figure\s*\d|"
    r"shown in (the )?(fig|figure|diagram)|"
    r"as shown(\s+in)?|"
    r"refer(s|red)?\s+to\s+(the\s+)?(fig|figure|diagram)|"
    r"in\s+the\s+(fig|figure|diagram)\s+below|"
    r"accompanying\s+(fig|figure|diagram)"
    r")",
    re.IGNORECASE,
)


def classify_figure_dependency(statement_md: str) -> FigureDependency:
    if _FIGURE_REFERENCE_PATTERN.search(statement_md):
        return FigureDependency.ESSENTIAL
    return FigureDependency.NONE


def run_figure_descope(session: Session, book_id: uuid.UUID) -> dict[str, int]:
    """Classifies figure_dependency for every SourceProblem of this book
    from statement text alone, and marks is_solvable=False for every
    ESSENTIAL one. Returns counts for reporting — callers should log
    these, since silently dropping problems without visibility into how
    many/why would hide the real cost of this v1 descope decision."""
    problems = (
        session.execute(select(SourceProblemORM).where(SourceProblemORM.book_id == book_id))
        .scalars()
        .all()
    )

    counts = {"none": 0, "essential_excluded": 0}
    for problem in problems:
        dependency = classify_figure_dependency(problem.statement_md)
        problem.figure_dependency = dependency
        if dependency == FigureDependency.ESSENTIAL:
            problem.is_solvable = False
            counts["essential_excluded"] += 1
        else:
            counts["none"] += 1

    session.flush()
    return counts
