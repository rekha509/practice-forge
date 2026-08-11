"""SSE progress stream — the real ETA the product spec asks for ("a real
ETA computed from observed pages/minute, not a fake spinner") is computed
here, at read time, from `JobORM.extraction_started_at` + `pages_done`:
rate = pages_done / elapsed_seconds, eta = (pages_total - pages_done) /
rate. Nothing is precomputed or hardcoded — a slow first page (e.g. a real
marker-pdf OCR pass, once that replaces today's pypdf placeholder) simply
produces a slower observed rate and a longer ETA, no code change needed.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from practice_forge.db.base import session_scope
from practice_forge.db.models import JobORM
from practice_forge.models.enums import JobStatus

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

POLL_INTERVAL_SECONDS = 0.5


def _pct(done: int | None, total: int | None) -> float | None:
    if done is None or not total:
        return None
    return round(100.0 * done / total, 1)


def _eta_seconds(job: JobORM) -> float | None:
    if job.stage != "extracting" or job.extraction_started_at is None:
        return None
    if not job.pages_done or not job.pages_total or job.pages_done >= job.pages_total:
        return None
    elapsed = (datetime.now(UTC) - job.extraction_started_at).total_seconds()
    if elapsed <= 0:
        return None
    rate = job.pages_done / elapsed  # real observed pages/second, not assumed
    if rate <= 0:
        return None
    return round((job.pages_total - job.pages_done) / rate, 1)


def job_status_payload(job: JobORM) -> dict[str, Any]:
    pct = (
        _pct(job.bytes_received, job.bytes_total)
        if job.stage == "uploading"
        else _pct(job.pages_done, job.pages_total)
        if job.stage == "extracting"
        else _pct(job.items_done, job.items_total)
    )
    return {
        "id": str(job.id),
        "kind": job.kind.value,
        "status": job.status.value,
        "stage": job.stage,
        "pct": pct,
        "bytes_received": job.bytes_received,
        "bytes_total": job.bytes_total,
        "pages_done": job.pages_done,
        "pages_total": job.pages_total,
        "items_done": job.items_done,
        "items_total": job.items_total,
        "eta_seconds": _eta_seconds(job),
        "error_message": job.error_message,
        "result_book_id": str(job.book_id) if job.book_id else None,
        "result_problem_set_id": str(job.result_problem_set_id) if job.result_problem_set_id else None,
    }


@router.get("/{job_id}")
def get_job(job_id: uuid.UUID) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
        return job_status_payload(job)


@router.get("/{job_id}/stream")
async def stream_job(job_id: uuid.UUID, request: Request) -> EventSourceResponse:
    async def event_generator() -> Any:
        last_sent: str | None = None
        while True:
            if await request.is_disconnected():
                return
            with session_scope() as session:
                job = session.get(JobORM, job_id)
                if job is None:
                    yield {"event": "error", "data": json.dumps({"error": "no such job"})}
                    return
                payload = job_status_payload(job)
                terminal = job.status in (JobStatus.DONE, JobStatus.FAILED)

            encoded = json.dumps(payload)
            if encoded != last_sent:
                yield {"event": "progress", "data": encoded}
                last_sent = encoded
            if terminal:
                return
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
