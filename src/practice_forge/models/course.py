"""Course is the scope for the no-repeat guarantee — deliberately not Book,
since a different book covering the same syllabus must still dedup against it."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Course(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    discipline_id: UUID
    faculty_name: str
    institution: str
