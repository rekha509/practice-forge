"""Variant is the shippable unit: an original rewrite of a ConceptCluster's
problem, its own generated code, and its own verified answer. source_ref is
internal faculty-facing provenance — it must never reach the student handout."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from practice_forge.models.enums import DifficultyLevel, ExtensionType, VerificationStatus


class SourceRef(BaseModel):
    book_title: str
    chapter: str | None = None
    page_no: int | None = None


class Variant(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    concept_cluster_id: UUID
    statement_md: str
    params: dict[str, Any]
    difficulty: DifficultyLevel
    topic_node_ids: list[UUID] = []
    solution_steps: list[str]  # numbered; code comments reference these numbers

    core_python_code: str
    extension_type: ExtensionType = ExtensionType.NONE
    extension_python_code: str | None = None
    extension_learning_notes: str | None = None
    extension_figure_paths: list[str] = []
    extension_metrics_json: dict[str, Any] | None = None

    verified_answer: str | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_log: list[str] = []

    needs_review: bool = False
    source_ref: SourceRef
    is_recycled: bool = False
