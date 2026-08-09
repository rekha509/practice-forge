"""Shared fixtures for tests that need the live Postgres container (already
required by Phase 1's docker-compose stack). Disciplines and topic nodes are
synced once per session. `db_session` truncates the tables tests write to at
setup, not just rollback at teardown — a prior manual `pf ingest` run (or a
crashed test that never got to roll back) leaves committed rows a rollback
alone can't clean up."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from practice_forge.db.base import get_session_factory
from practice_forge.db.models import BookORM, PageORM, SectionORM, SourceProblemORM
from practice_forge.profiles.sync import sync_disciplines, sync_topic_nodes


@pytest.fixture(scope="session", autouse=True)
def _synced_disciplines() -> None:
    session = get_session_factory()()
    try:
        sync_disciplines(session)
        sync_topic_nodes(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = get_session_factory()()
    # FK order: source_problems/sections reference books; pages reference books.
    session.execute(delete(SourceProblemORM))
    session.execute(delete(SectionORM))
    session.execute(delete(PageORM))
    session.execute(delete(BookORM))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
