"""Discipline and TopicNode: the declarative backbone that keeps discipline
differences out of pipeline code (see profiles/*.yaml)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from practice_forge.models.enums import ExtensionType


class Discipline(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    display_name: str
    solver_libs: list[str]
    ml_libs: list[str]
    allowed_extension_types: list[ExtensionType]
    sandbox_image_tag: str


class TopicNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    discipline_id: UUID
    parent_id: UUID | None = None
    name: str
    aliases: list[str] = []
    syllabus_code: str | None = None
