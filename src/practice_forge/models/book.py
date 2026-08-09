"""Book, Page, Section — the raw ingest layer. Book carries both dedup keys:
file_sha256 for exact-file dedup and minhash_signature for cross-scan/edition dedup."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from practice_forge.models.enums import IngestStatus


class Book(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    authors: list[str]
    edition: str | None = None
    discipline_id: UUID
    page_count: int
    ingest_status: IngestStatus = IngestStatus.PENDING
    file_sha256: str
    minhash_signature: list[int] = []
    canonical_book_id: UUID | None = None
    uploaded_by: str


class Page(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    book_id: UUID
    page_no: int
    markdown: str
    has_math: bool = False
    has_figure: bool = False
    unit_system_detected: str | None = None  # e.g. "SI", "Indian-mixed", "imperial"
    extraction_confidence: float


class Section(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    book_id: UUID
    chapter_no: int | None = None
    title: str
    page_start: int
    page_end: int
    topic_node_ids: list[UUID] = []
