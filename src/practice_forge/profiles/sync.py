"""Upserts declarative profiles/*.yaml into the disciplines table.

Book.discipline_id is a real FK — something has to bridge the declarative
config into rows the rest of the schema can reference. Discipline IDs are
deterministic (uuid5 of the profile key) so re-running this is idempotent
and the same discipline always gets the same id across environments.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import DisciplineORM
from practice_forge.profiles.loader import DisciplineProfile, list_profiles


def discipline_id_for_key(key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"practice-forge.discipline.{key}")


def sync_disciplines(session: Session) -> list[DisciplineProfile]:
    profiles = list_profiles()
    for profile in profiles:
        discipline_id = discipline_id_for_key(profile.key)
        existing = session.execute(
            select(DisciplineORM).where(DisciplineORM.id == discipline_id)
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                DisciplineORM(
                    id=discipline_id,
                    key=profile.key,
                    display_name=profile.display_name,
                    solver_libs=profile.solver_libs,
                    ml_libs=profile.ml_libs,
                    allowed_extension_types=[e.value for e in profile.allowed_extension_types],
                    sandbox_image_tag=profile.sandbox_image_tag,
                )
            )
        else:
            existing.display_name = profile.display_name
            existing.solver_libs = profile.solver_libs
            existing.ml_libs = profile.ml_libs
            existing.allowed_extension_types = [e.value for e in profile.allowed_extension_types]
            existing.sandbox_image_tag = profile.sandbox_image_tag
    session.flush()
    return list(profiles)
