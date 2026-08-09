"""ProblemSet is the rendered artifact; IssuedLedger is the no-repeat guarantee's
ground truth. A row is written ONLY after both PDFs render successfully (S10) —
never speculatively, so a failed render can't poison future selection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProblemSet(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    title: str
    run_number: int
    variant_ids: list[UUID]
    typst_source: str
    student_pdf_path: str
    solutions_pdf_path: str
    created_at: datetime


class IssuedLedger(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    concept_cluster_id: UUID
    variant_id: UUID
    problem_set_id: UUID
    issued_at: datetime
