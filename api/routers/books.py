"""Library + resumable chunked upload.

The upload endpoints implement the CORE of the tus protocol (creation,
`Upload-Offset` head/patch, offset-mismatch conflict) — not the full
protocol (no auth/expiration/checksum extensions). That's enough for real
resumability: if a connection drops mid-upload, the client HEADs to learn
how many bytes actually landed, then PATCHes the rest from there. Nothing
is re-processed or re-uploaded.

Dedup ordering (see `ingest/pipeline.py::run_ingest_resumable`'s
docstring): the exact-sha256 check only runs once the full file is
assembled and `ingest_task` starts — a chunked upload has no way to know
the file is a byte-for-byte duplicate before it's fully received, since
the hash is over the complete file. This is a real, disclosed limit: for
THIS transport, "reject nothing on page count" and "dedup before
processing" both hold (nothing about upload speed depends on page count,
and the ingest task itself still dedups before touching the DB), but a
verbatim re-upload isn't short-circuited mid-transfer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from practice_forge.config import REPO_ROOT
from practice_forge.db.models import (
    BookORM,
    ConceptCardORM,
    ConceptClusterORM,
    JobORM,
    SectionORM,
)
from practice_forge.models.enums import JobKind, JobStatus
from worker.tasks import ingest_task

from ..deps import get_db
from ..schemas import (
    BookDetail,
    BookListItem,
    InitiateUploadRequest,
    InitiateUploadResponse,
    SectionSummary,
)

router = APIRouter(prefix="/api/books", tags=["books"])

UPLOAD_DIR = REPO_ROOT / "data" / "uploads"


def _now() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=InitiateUploadResponse, status_code=status.HTTP_201_CREATED)
def initiate_upload(req: InitiateUploadRequest, db: Session = Depends(get_db)) -> InitiateUploadResponse:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4()
    upload_path = UPLOAD_DIR / f"{job_id}.pdf"
    upload_path.write_bytes(b"")  # pre-allocate so PATCH can seek into it

    job = JobORM(
        id=job_id,
        kind=JobKind.INGEST,
        status=JobStatus.UPLOADING,
        stage="uploading",
        bytes_received=0,
        bytes_total=req.total_bytes,
        upload_path=str(upload_path),
        discipline_key=req.discipline,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    return InitiateUploadResponse(job_id=job_id, chunk_url=f"/api/books/{job_id}/chunk")


@router.head("/{job_id}/chunk")
def upload_chunk_offset(job_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    job = db.get(JobORM, job_id)
    if job is None or job.kind != JobKind.INGEST:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such upload")
    return Response(headers={"Upload-Offset": str(job.bytes_received or 0)})


@router.patch("/{job_id}/chunk")
async def upload_chunk(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> Response:
    job = db.get(JobORM, job_id)
    if job is None or job.kind != JobKind.INGEST:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such upload")
    if job.status != JobStatus.UPLOADING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload already completed")

    offset_header = request.headers.get("Upload-Offset")
    if offset_header is None or not offset_header.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing/invalid Upload-Offset header")
    offset = int(offset_header)
    if offset != job.bytes_received:
        # Real tus semantics: the client's view of how much landed is
        # stale — it must HEAD first to learn the true offset and resume
        # from there, not guess.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Upload-Offset {offset} does not match {job.bytes_received} bytes actually received",
        )

    assert job.upload_path is not None
    upload_path = job.upload_path
    # Reading the request body is genuinely async (Starlette's own
    # stream); the file write is NOT, so it's offloaded to a thread pool
    # rather than blocking the event loop for the duration of a
    # potentially large chunk write.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)

    def _write_at_offset() -> int:
        with open(upload_path, "r+b") as f:
            f.seek(offset)
            f.write(body)
        return len(body)

    written = await run_in_threadpool(_write_at_offset)

    job.bytes_received = (job.bytes_received or 0) + written
    job.updated_at = _now()

    if job.bytes_received >= (job.bytes_total or 0):
        job.status = JobStatus.QUEUED
        job.stage = "queued"
        db.commit()
        ingest_task.delay(str(job.id))
    else:
        db.commit()

    return Response(headers={"Upload-Offset": str(job.bytes_received)})


@router.get("", response_model=list[BookListItem])
def list_books(db: Session = Depends(get_db)) -> list[BookListItem]:
    books = db.execute(select(BookORM)).scalars().all()
    items: list[BookListItem] = []
    for book in books:
        concept_count = db.execute(
            select(func.count())
            .select_from(ConceptClusterORM)
            .join(ConceptCardORM, ConceptClusterORM.representative_card_id == ConceptCardORM.id)
            .where(ConceptCardORM.book_id == book.id)
        ).scalar_one()
        items.append(
            BookListItem(
                id=book.id,
                title=book.title,
                page_count=book.page_count,
                ingest_status=book.ingest_status.value,
                concept_count=concept_count,
            )
        )
    return items


@router.get("/{book_id}", response_model=BookDetail)
def get_book(book_id: uuid.UUID, db: Session = Depends(get_db)) -> BookDetail:
    book = db.get(BookORM, book_id)
    if book is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such book")

    sections = db.execute(
        select(SectionORM).where(SectionORM.book_id == book_id).order_by(SectionORM.page_start)
    ).scalars().all()

    summaries: list[SectionSummary] = []
    for section in sections:
        problem_count = db.execute(
            select(func.count())
            .select_from(ConceptClusterORM)
            .join(ConceptCardORM, ConceptClusterORM.representative_card_id == ConceptCardORM.id)
            .where(ConceptCardORM.section_id == section.id)
        ).scalar_one()
        summaries.append(
            SectionSummary(
                id=section.id,
                chapter_no=section.chapter_no,
                title=section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                problem_count=problem_count,
            )
        )

    return BookDetail(
        id=book.id,
        title=book.title,
        authors=book.authors,
        page_count=book.page_count,
        ingest_status=book.ingest_status.value,
        sections=summaries,
    )
