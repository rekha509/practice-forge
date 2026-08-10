"""Shared fixtures for tests that need a live Postgres container (already
required by Phase 1's docker-compose stack). Uses its OWN database
(`TEST_DATABASE_URL`, default `practice_forge_test`) — never the same
database real ingested content lives in. `db_session` truncates tables at
setup, not just rollback at teardown, so a prior crashed test (or a stray
manual write against the test DB) can't leave rows a rollback alone
wouldn't clean up — but that blast radius is now confined to the test
database, not whatever's been ingested for real. (Discovered why this
separation matters the hard way: an earlier version of this fixture
pointed at the same database as `pf ingest`, and running the suite wiped
out a real book mid-session.)
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from practice_forge.config import get_settings
from practice_forge.db.base import make_session_factory
from practice_forge.db.models import (
    BookORM,
    CandidateScoreORM,
    ConceptCardORM,
    ConceptClusterORM,
    PageORM,
    SectionORM,
    SourceProblemORM,
)
from practice_forge.profiles.sync import sync_disciplines, sync_topic_nodes

_test_session_factory = make_session_factory(get_settings().test_database_url)


@pytest.fixture(scope="session", autouse=True)
def _synced_disciplines() -> None:
    session = _test_session_factory()
    try:
        sync_disciplines(session)
        sync_topic_nodes(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def db_session() -> Iterator[Session]:
    session = _test_session_factory()
    # FK order: candidate_scores/concept_clusters reference concept_cards;
    # concept_cards/source_problems/sections reference books; pages
    # reference books. concept_clusters is discipline-scoped, not
    # book-scoped (see concepts.py's _cluster_cards) — must be cleared too,
    # or a stale cluster from a prior test's run could wrongly "match" a
    # fresh test's card via the cross-run clustering path.
    session.execute(delete(CandidateScoreORM))
    session.execute(delete(ConceptClusterORM))
    session.execute(delete(ConceptCardORM))
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
