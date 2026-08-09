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

from practice_forge.db.models import DisciplineORM, TopicNodeORM
from practice_forge.profiles.loader import DisciplineProfile, list_profiles


def discipline_id_for_key(key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"practice-forge.discipline.{key}")


def topic_node_id_for(discipline_key: str, topic_name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"practice-forge.topic.{discipline_key}.{topic_name}")


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


def sync_topic_nodes(session: Session) -> None:
    """Seeds a flat TopicNode per profile topic (no hierarchy yet — S2's
    syllabus-code/parent structure is a future refinement, not needed for
    Section->TopicNode matching to work)."""
    for profile in list_profiles():
        discipline_id = discipline_id_for_key(profile.key)
        for topic_name in profile.topics:
            topic_id = topic_node_id_for(profile.key, topic_name)
            existing = session.execute(
                select(TopicNodeORM).where(TopicNodeORM.id == topic_id)
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    TopicNodeORM(
                        id=topic_id,
                        discipline_id=discipline_id,
                        parent_id=None,
                        name=topic_name,
                        aliases=[],
                        syllabus_code=None,
                    )
                )
    session.flush()
