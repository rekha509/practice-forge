"""SourceProblem is internal-only provenance: a template for variant generation,
never rendered into shipped output (see COPYRIGHT policy)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from practice_forge.models.enums import FigureDependency, ProblemKind


class SourceProblem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    book_id: UUID
    section_id: UUID
    page_no: int
    kind: ProblemKind
    statement_md: str
    given: list[str] = []
    find: list[str] = []
    solution_md: str | None = None
    final_answer: str | None = None
    figure_ids: list[UUID] = []
    figure_dependency: FigureDependency = FigureDependency.NONE
    is_solvable: bool = True
