"""S1 orchestration: exact-hash dedup -> MinHash cross-edition dedup ->
extract + persist. Idempotent and resumable:

- Same file re-ingested after a completed run -> dedup hit, nothing written.
- Same file re-ingested after a run that crashed mid-extraction -> resumes,
  persisting only pages that aren't already there.
- A different scan/reprint of an already-ingested book -> dedup hit via
  MinHash + metadata match, nothing written, no second Book row created.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from datasketch import MinHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.db.models import BookORM, DisciplineORM, PageORM
from practice_forge.ingest.extract import PageExtraction, extract_pages, iter_pages, page_count
from practice_forge.ingest.hashing import sha256_file
from practice_forge.ingest.metadata import BookMetadata, extract_metadata, metadata_matches
from practice_forge.ingest.minhash import (
    build_minhash,
    jaccard,
    list_to_minhash,
    signature_to_list,
)
from practice_forge.models.enums import IngestStatus

JACCARD_DEDUP_THRESHOLD = 0.8
PAGE_COUNT_TOLERANCE = 2
METADATA_SAMPLE_PAGES = 5


@dataclass(frozen=True)
class IngestResult:
    book_id: uuid.UUID
    dedup_hit: str | None  # None, "exact_sha256", "minhash_edition", or "resumed"
    pages_ingested: int


def run_ingest(
    session: Session,
    pdf_path: Path,
    *,
    discipline_key: str,
    uploaded_by: str,
) -> IngestResult:
    discipline = session.execute(
        select(DisciplineORM).where(DisciplineORM.key == discipline_key)
    ).scalar_one_or_none()
    if discipline is None:
        raise ValueError(
            f"Unknown discipline key {discipline_key!r} — run `pf profiles sync` first."
        )

    file_hash = sha256_file(pdf_path)
    existing_by_hash = session.execute(
        select(BookORM).where(BookORM.file_sha256 == file_hash)
    ).scalar_one_or_none()

    if existing_by_hash is not None and existing_by_hash.ingest_status == IngestStatus.DONE:
        return IngestResult(
            book_id=existing_by_hash.canonical_book_id or existing_by_hash.id,
            dedup_hit="exact_sha256",
            pages_ingested=0,
        )

    pages = extract_pages(str(pdf_path))

    if existing_by_hash is not None:
        # Resuming a partial ingest from a previous crashed/killed run.
        return _resume_partial_ingest(session, existing_by_hash, pages)

    page_count = len(pages)
    sample_texts = [p.markdown for p in pages[:METADATA_SAMPLE_PAGES]]
    metadata = extract_metadata("\n".join(sample_texts))
    minhash = build_minhash([p.markdown for p in pages])

    canonical_match = _find_canonical_match(session, discipline.id, metadata, minhash, page_count)
    if canonical_match is not None:
        return IngestResult(book_id=canonical_match, dedup_hit="minhash_edition", pages_ingested=0)

    book = BookORM(
        id=uuid.uuid4(),
        title=metadata.title,
        authors=metadata.authors,
        edition=metadata.edition,
        discipline_id=discipline.id,
        page_count=page_count,
        ingest_status=IngestStatus.EXTRACTING,
        file_sha256=file_hash,
        minhash_signature=signature_to_list(minhash),
        canonical_book_id=None,
        uploaded_by=uploaded_by,
    )
    session.add(book)
    session.flush()

    _persist_pages(session, book.id, pages, already_present=set())
    book.ingest_status = IngestStatus.DONE
    session.flush()

    return IngestResult(book_id=book.id, dedup_hit=None, pages_ingested=page_count)


def _resume_partial_ingest(
    session: Session, book: BookORM, pages: list[PageExtraction]
) -> IngestResult:
    already_present = set(
        session.execute(
            select(PageORM.page_no).where(PageORM.book_id == book.id)
        ).scalars().all()
    )
    newly_persisted = _persist_pages(session, book.id, pages, already_present)
    book.ingest_status = IngestStatus.DONE
    session.flush()
    return IngestResult(book_id=book.id, dedup_hit="resumed", pages_ingested=newly_persisted)


def _persist_pages(
    session: Session,
    book_id: uuid.UUID,
    pages: list[PageExtraction],
    already_present: set[int],
) -> int:
    count = 0
    for page in pages:
        if page.page_no in already_present:
            continue
        session.add(
            PageORM(
                id=uuid.uuid4(),
                book_id=book_id,
                page_no=page.page_no,
                markdown=page.markdown,
                has_math=page.has_math,
                has_figure=page.has_figure,
                unit_system_detected=page.unit_system_detected,
                extraction_confidence=page.extraction_confidence,
            )
        )
        count += 1
    session.flush()
    return count


def run_ingest_resumable(
    session: Session,
    pdf_path: Path,
    *,
    discipline_key: str,
    uploaded_by: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> IngestResult:
    """For the API's async ingest job (`worker/tasks.py`), not the `pf
    ingest` CLI (which stays on `run_ingest` above, unchanged).

    Real difference from `run_ingest`: persists pages one at a time with a
    genuine `session.commit()` after EACH page (not `_persist_pages`'s
    single flush-at-the-end), calling `progress_cb(pages_done,
    pages_total)` after every commit. That's what actually makes a mid-run
    crash resumable — `_persist_pages`'s flush alone leaves everything in
    one uncommitted transaction that a crash rolls back wholesale (Postgres
    itself discards an uncommitted transaction when the connection dies),
    so `run_ingest`'s own "resumable" framing only really holds ACROSS
    separate completed CLI invocations, not a genuine mid-extraction crash.

    Dedup ordering (see module docstring's real caveat, unchanged from
    `run_ingest`): exact sha256 is checked before ANY extraction — a
    verbatim re-upload skips straight to "ready," zero processing. MinHash
    cross-edition dedup needs every page's text to build a signature, so
    it's checked after a full in-memory extraction pass but before any
    PageORM/Book row is written — a content-duplicate book is never
    persisted, but the extraction pass itself still runs first. Fast today
    with the pypdf placeholder extractor (docs/adr/0004); would need
    revisiting if/when real marker-pdf (genuinely slow, page-by-page OCR)
    replaces it, since then a full pass before any dedup decision could
    itself become the expensive step MinHash dedup exists to avoid.
    """
    cb: Callable[[int, int], None] = progress_cb or (lambda _done, _total: None)

    discipline = session.execute(
        select(DisciplineORM).where(DisciplineORM.key == discipline_key)
    ).scalar_one_or_none()
    if discipline is None:
        raise ValueError(
            f"Unknown discipline key {discipline_key!r} — run `pf profiles sync` first."
        )

    file_hash = sha256_file(pdf_path)
    existing_by_hash = session.execute(
        select(BookORM).where(BookORM.file_sha256 == file_hash)
    ).scalar_one_or_none()

    if existing_by_hash is not None and existing_by_hash.ingest_status == IngestStatus.DONE:
        return IngestResult(
            book_id=existing_by_hash.canonical_book_id or existing_by_hash.id,
            dedup_hit="exact_sha256",
            pages_ingested=0,
        )

    total_pages = page_count(str(pdf_path))
    pages = list(iter_pages(str(pdf_path)))  # fast today (pypdf) — see docstring

    if existing_by_hash is not None:
        already_present = set(
            session.execute(
                select(PageORM.page_no).where(PageORM.book_id == existing_by_hash.id)
            )
            .scalars()
            .all()
        )
        newly_persisted = _persist_pages_with_progress(
            session, existing_by_hash.id, pages, already_present, total_pages, cb
        )
        existing_by_hash.ingest_status = IngestStatus.DONE
        session.commit()
        return IngestResult(
            book_id=existing_by_hash.id, dedup_hit="resumed", pages_ingested=newly_persisted
        )

    sample_texts = [p.markdown for p in pages[:METADATA_SAMPLE_PAGES]]
    metadata = extract_metadata("\n".join(sample_texts))
    minhash = build_minhash([p.markdown for p in pages])

    canonical_match = _find_canonical_match(session, discipline.id, metadata, minhash, total_pages)
    if canonical_match is not None:
        return IngestResult(book_id=canonical_match, dedup_hit="minhash_edition", pages_ingested=0)

    book = BookORM(
        id=uuid.uuid4(),
        title=metadata.title,
        authors=metadata.authors,
        edition=metadata.edition,
        discipline_id=discipline.id,
        page_count=total_pages,
        ingest_status=IngestStatus.EXTRACTING,
        file_sha256=file_hash,
        minhash_signature=signature_to_list(minhash),
        canonical_book_id=None,
        uploaded_by=uploaded_by,
    )
    session.add(book)
    session.commit()

    newly_persisted = _persist_pages_with_progress(session, book.id, pages, set(), total_pages, cb)
    book.ingest_status = IngestStatus.DONE
    session.commit()

    return IngestResult(book_id=book.id, dedup_hit=None, pages_ingested=newly_persisted)


def _persist_pages_with_progress(
    session: Session,
    book_id: uuid.UUID,
    pages: list[PageExtraction],
    already_present: set[int],
    total_pages: int,
    progress_cb: Callable[[int, int], None],
) -> int:
    count = 0
    done = len(already_present)
    progress_cb(done, total_pages)
    for page in pages:
        if page.page_no in already_present:
            continue
        session.add(
            PageORM(
                id=uuid.uuid4(),
                book_id=book_id,
                page_no=page.page_no,
                markdown=page.markdown,
                has_math=page.has_math,
                has_figure=page.has_figure,
                unit_system_detected=page.unit_system_detected,
                extraction_confidence=page.extraction_confidence,
            )
        )
        session.commit()
        count += 1
        done += 1
        progress_cb(done, total_pages)
    return count


def _find_canonical_match(
    session: Session,
    discipline_id: uuid.UUID,
    metadata: BookMetadata,
    minhash: MinHash,
    page_count: int,
) -> uuid.UUID | None:
    candidates = (
        session.execute(
            select(BookORM).where(
                BookORM.discipline_id == discipline_id,
                BookORM.ingest_status == IngestStatus.DONE,
            )
        )
        .scalars()
        .all()
    )

    for candidate in candidates:
        if abs(candidate.page_count - page_count) > PAGE_COUNT_TOLERANCE:
            continue
        candidate_metadata = BookMetadata(
            title=candidate.title, authors=candidate.authors, edition=candidate.edition
        )
        if not metadata_matches(metadata, candidate_metadata):
            continue
        candidate_minhash = list_to_minhash(candidate.minhash_signature)
        if jaccard(minhash, candidate_minhash) >= JACCARD_DEDUP_THRESHOLD:
            return candidate.canonical_book_id or candidate.id
    return None
