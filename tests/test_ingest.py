"""Phase 2 gate: exact-file dedup, cross-edition MinHash dedup, and
idempotent/resumable page persistence (S1)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, PageORM
from practice_forge.ingest.pipeline import run_ingest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_fresh_ingest_persists_book_and_pages(db_session: Session) -> None:
    result = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    assert result.dedup_hit is None
    assert result.pages_ingested == 8

    book = db_session.get(BookORM, result.book_id)
    assert book is not None
    assert book.title == "Strength of Materials"
    assert "R.S. Khurmi" in book.authors[0]

    pages = db_session.execute(
        select(PageORM).where(PageORM.book_id == result.book_id)
    ).scalars().all()
    assert len(pages) == 8


def test_same_file_reingested_is_exact_hash_dedup_hit(db_session: Session) -> None:
    first = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    second = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )

    assert second.dedup_hit == "exact_sha256"
    assert second.book_id == first.book_id
    assert second.pages_ingested == 0

    book_count = db_session.execute(select(BookORM)).scalars().all()
    assert len(book_count) == 1


def test_different_scan_of_same_book_is_minhash_dedup_hit(db_session: Session) -> None:
    first = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    second = run_ingest(
        db_session,
        FIXTURES / "sample_rescan.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )

    assert second.dedup_hit == "minhash_edition"
    assert second.book_id == first.book_id

    book_count = db_session.execute(select(BookORM)).scalars().all()
    assert len(book_count) == 1


def test_genuinely_different_book_is_not_deduped(db_session: Session) -> None:
    first = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    second = run_ingest(
        db_session,
        FIXTURES / "other_book.pdf",
        discipline_key="electrical",
        uploaded_by="test",
    )

    assert second.dedup_hit is None
    assert second.book_id != first.book_id

    book_count = db_session.execute(select(BookORM)).scalars().all()
    assert len(book_count) == 2


def test_resumes_partial_ingest_without_redoing_persisted_pages(db_session: Session) -> None:
    from practice_forge.models.enums import IngestStatus

    first = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )

    # Simulate a crash mid-extraction: drop half the pages, mark incomplete.
    book = db_session.get(BookORM, first.book_id)
    assert book is not None
    book.ingest_status = IngestStatus.EXTRACTING
    stray_pages = db_session.execute(
        select(PageORM).where(PageORM.book_id == first.book_id)
    ).scalars().all()
    for page in stray_pages[4:]:
        db_session.delete(page)
    db_session.flush()

    remaining = db_session.execute(
        select(PageORM).where(PageORM.book_id == first.book_id)
    ).scalars().all()
    assert len(remaining) == 4

    resumed = run_ingest(
        db_session,
        FIXTURES / "sample.pdf",
        discipline_key="mechanical",
        uploaded_by="test",
    )
    assert resumed.dedup_hit == "resumed"
    assert resumed.book_id == first.book_id
    assert resumed.pages_ingested == 4  # only the missing ones were re-persisted

    final_pages = db_session.execute(
        select(PageORM).where(PageORM.book_id == first.book_id)
    ).scalars().all()
    assert len(final_pages) == 8

    final_book = db_session.get(BookORM, first.book_id)
    assert final_book is not None
    assert final_book.ingest_status == IngestStatus.DONE
