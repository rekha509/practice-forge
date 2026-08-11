"""Minimum viable auth (docs/adr/0010): a per-faculty bearer token, no
passwords, no sessions. Distinguishes who is asking so IssuedLedger writes
scope to the right Course — nothing more.

Read-only endpoints (library, job status, PDF/zip downloads) don't
require a token. Endpoints that mutate a Course's ledger (generate,
reshuffle, new-set) do, via `get_current_faculty` + `require_course_owner`.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import CourseORM, FacultyORM

from .deps import get_db

_bearer = HTTPBearer(auto_error=False)


def get_current_faculty(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> FacultyORM:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    faculty = db.execute(
        select(FacultyORM).where(FacultyORM.token == credentials.credentials)
    ).scalar_one_or_none()
    if faculty is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return faculty


def require_course_owner(course: CourseORM, faculty: FacultyORM) -> None:
    """An unclaimed legacy course (faculty_id is None — e.g. one created
    before this decision existed) is treated as ownable by whoever asks
    first at the API layer; that's a real, disclosed simplification (see
    docs/adr/0010), not a security guarantee for such courses."""
    if course.faculty_id is not None and course.faculty_id != faculty.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This course belongs to a different faculty account"
        )
