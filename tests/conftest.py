"""Shared fixtures for tests that need the live Postgres container (already
required by Phase 1's docker-compose stack). Disciplines are synced once per
session. `db_session` truncates Book/Page at setup, not just rollback at
teardown — a prior manual `pf ingest` run (or a crashed test that never got
to roll back) leaves committed rows a rollback alone can't clean up."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from practice_forge.db.base import get_session_factory
from practice_forge.db.models import BookORM, PageORM
from practice_forge.profiles.sync import sync_disciplines


@pytest.fixture(scope="session", autouse=True)
def _synced_disciplines() -> None:
    session = get_session_factory()()
    try:
        sync_disciplines(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = get_session_factory()()
    session.execute(delete(PageORM))
    session.execute(delete(BookORM))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
