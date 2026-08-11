"""`run_ingest_resumable` — the API/worker path (P10), distinct from
`run_ingest` (the `pf ingest` CLI path, unchanged, still covered by
test_ingest.py).

The load-bearing test here is the crash-resume one: it proves pages are
DURABLY committed one at a time (via a genuine `session.commit()` inside
the persistence loop), not just flushed within one larger transaction a
crash would roll back wholesale — that distinction is the entire point of
this function existing separately from `run_ingest`."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, PageORM
from practice_forge.ingest.pipeline import run_ingest_resumable
from practice_forge.models.enums import IngestStatus

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class _SimulatedCrash(Exception):
    pass


def test_fresh_ingest_calls_progress_after_every_real_commit(db_session: Session) -> None:
    calls: list[tuple[int, int]] = []
    result = run_ingest_resumable(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
        progress_cb=lambda done, total: calls.append((done, total)),
    )

    assert result.dedup_hit is None
    assert result.pages_ingested == 8
    # One call before any page (0, 8), then one per page through (8, 8).
    assert calls == [(i, 8) for i in range(9)]

    book = db_session.get(BookORM, result.book_id)
    assert book is not None
    assert book.ingest_status == IngestStatus.DONE


def test_exact_hash_dedup_still_skips_before_any_extraction(db_session: Session) -> None:
    first = run_ingest_resumable(
        db_session, FIXTURES / "sample.pdf", discipline_key="mechanical", uploaded_by="test"
    )
    second = run_ingest_resumable(
        db_session, FIXTURES / "sample.pdf", discipline_key="mechanical", uploaded_by="test"
    )
    assert second.dedup_hit == "exact_sha256"
    assert second.book_id == first.book_id
    assert second.pages_ingested == 0


def test_crash_mid_ingest_leaves_already_committed_pages_durable_and_resumes(
    db_session: Session,
) -> None:
    def crash_after_four(done: int, _total: int) -> None:
        if done == 4:
            raise _SimulatedCrash()

    with pytest.raises(_SimulatedCrash):
        run_ingest_resumable(
            db_session,
            FIXTURES / "sample.pdf",
            discipline_key="mechanical",
            uploaded_by="test",
            progress_cb=crash_after_four,
        )

    # Nothing in this test explicitly committed anything — if these rows
    # are visible, it's because run_ingest_resumable itself committed them
    # BEFORE the simulated crash, proving real per-page durability.
    book = db_session.execute(select(BookORM)).scalars().one()
    assert book.ingest_status == IngestStatus.EXTRACTING  # never reached DONE
    pages_after_crash = db_session.execute(
        select(PageORM).where(PageORM.book_id == book.id)
    ).scalars().all()
    assert len(pages_after_crash) == 4

    resumed = run_ingest_resumable(
        db_session, FIXTURES / "sample.pdf", discipline_key="mechanical", uploaded_by="test"
    )
    assert resumed.dedup_hit == "resumed"
    assert resumed.book_id == book.id
    assert resumed.pages_ingested == 4  # only the missing 4 were re-persisted

    final_pages = db_session.execute(
        select(PageORM).where(PageORM.book_id == book.id)
    ).scalars().all()
    assert len(final_pages) == 8
    final_book = db_session.get(BookORM, book.id)
    assert final_book is not None
    assert final_book.ingest_status == IngestStatus.DONE


def test_different_scan_of_same_book_is_minhash_dedup_hit(db_session: Session) -> None:
    first = run_ingest_resumable(
        db_session, FIXTURES / "sample.pdf", discipline_key="mechanical", uploaded_by="test"
    )
    second = run_ingest_resumable(
        db_session, FIXTURES / "sample_rescan.pdf", discipline_key="mechanical", uploaded_by="test"
    )
    assert second.dedup_hit == "minhash_edition"
    assert second.book_id == first.book_id

    book_count = db_session.execute(select(BookORM)).scalars().all()
    assert len(book_count) == 1
