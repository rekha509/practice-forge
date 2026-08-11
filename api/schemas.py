"""Pydantic request/response models for the P10 API. Kept separate from
`practice_forge.db.models` (the ORM layer) deliberately — these describe
the wire shape, not the storage shape, and the two are allowed to diverge
(e.g. a book's `concept_count` here is a computed aggregate, not a column)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InitiateUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    total_bytes: int = Field(gt=0)
    discipline: str


class InitiateUploadResponse(BaseModel):
    job_id: uuid.UUID
    chunk_url: str


class BookListItem(BaseModel):
    id: uuid.UUID
    title: str
    page_count: int
    ingest_status: str
    concept_count: int


class SectionSummary(BaseModel):
    id: uuid.UUID
    chapter_no: int | None
    title: str
    page_start: int
    page_end: int
    problem_count: int


class BookDetail(BaseModel):
    id: uuid.UUID
    title: str
    authors: list[str]
    page_count: int
    ingest_status: str
    sections: list[SectionSummary]


class JobStatusOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    stage: str
    pct: float | None
    bytes_received: int | None
    bytes_total: int | None
    pages_done: int | None
    pages_total: int | None
    items_done: int | None
    items_total: int | None
    eta_seconds: float | None
    error_message: str | None
    result_book_id: uuid.UUID | None
    result_problem_set_id: uuid.UUID | None


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: uuid.UUID
    course_id: uuid.UUID
    # None or [] => whole book (the default, per spec).
    section_ids: list[uuid.UUID] | None = None
    count: int = Field(default=20, gt=0)
    difficulty_mix: dict[str, int] | None = None


class ProblemSetSummary(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    title: str
    run_number: int
    problem_count: int
    created_at: datetime


class ProblemPreview(BaseModel):
    index: int
    name: str
    statement_md: str
    difficulty: str
    solution_steps: list[str]
    core_python_code: str
    verified_answer: str | None
    extension_type: str


class ProblemSetDetail(ProblemSetSummary):
    problems: list[ProblemPreview]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_index: int
    step_index: int
    question: str
