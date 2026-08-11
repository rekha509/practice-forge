"""P10's real gate: a genuine upload-to-PDF run through actual HTTP
sockets, with real SSE progress observed while a real, separate Celery
worker subprocess (consuming a real Redis queue) does the work — not
TestClient's in-process ASGI transport, and not a mocked task.

Marked `@pytest.mark.e2e` (spawns real subprocesses, needs a real Docker
sandbox) and `@pytest.mark.llm` (the generate half makes real Gemini
calls) — both excluded from the default `pytest` run (see pyproject.toml)
since neither belongs in a routine, no-external-dependencies suite. Run
explicitly:

    pytest tests/test_api_e2e.py -m e2e -v -s

Deliberately targets the REAL dev database (DATABASE_URL), not the
isolated test DB every other test in this suite uses — the whole point is
proving the deployed shape works, and the "generate" half needs a book
that has already been through the real (LLM-costly) S2-S7 pipeline.
Two real, disclosed economy choices, so this doesn't repeat work already
proven elsewhere via the CLI or spend more real quota than proving this
NEW layer needs:

1. The chunked-upload / ingest / SSE mechanics are proven against the
   small, real 8-page `tests/fixtures/sample.pdf` — ingest makes no LLM
   call at all, so this part is fast and free regardless of how many
   times it's re-run (a repeat run just hits the real exact-sha256 dedup
   path, also asserted here).
2. The generate-to-PDF mechanics are proven against the REAL, already-
   distilled/scored 781-page Nag thermodynamics book (id
   4d97664c-50ee-4c77-83b8-7951efae4d60, 288 real concept clusters from
   earlier sessions) with `count=1` — the minimum that still exercises a
   real S8 (variant) + S9 (codegen + Docker sandbox verify) + S10
   (render) call, rather than re-running the multi-hour, multi-day S2-S7
   pipeline against a fresh upload just to prove THIS layer.

This also finally creates the real Course this project queued in an
earlier session ("AI/ML for Mechanical Systems", faculty Mahesh,
institution RGUKT Basar — real, user-provided values) if it doesn't
already exist. Idempotent: safe to re-run without duplicating it.
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from practice_forge.config import REPO_ROOT
from practice_forge.db.base import session_scope
from practice_forge.db.models import (
    BookORM,
    CourseORM,
    DisciplineORM,
    FacultyORM,
    IssuedLedgerORM,
)

pytestmark = [pytest.mark.e2e, pytest.mark.llm]

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BIG_BOOK_ID = uuid.UUID("4d97664c-50ee-4c77-83b8-7951efae4d60")
REAL_COURSE_NAME = "AI/ML for Mechanical Systems"
REAL_FACULTY_NAME = "Mahesh"
REAL_INSTITUTION = "RGUKT Basar"

STARTUP_TIMEOUT_S = 60
JOB_TIMEOUT_S = 180


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def live_server() -> Iterator[str]:
    """A real uvicorn subprocess serving api.main:app over a real TCP
    socket — not TestClient's in-process ASGI transport."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO_ROOT),
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    ready = False
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/healthz", timeout=1)
            if r.status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    if not ready:
        proc.terminate()
        proc.wait(timeout=10)
        raise RuntimeError("uvicorn did not become ready in time")
    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def celery_worker_process() -> Iterator[subprocess.Popen[bytes]]:
    """A real Celery worker subprocess consuming the real Redis broker —
    `--pool=solo` since prefork isn't available on Windows. Readiness is
    checked via a real `control.ping()`, not a fixed sleep."""
    from worker.celery_app import celery_app

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "worker.celery_app.celery_app",
            "worker",
            "--loglevel=info",
            "--pool=solo",
        ],
        cwd=str(REPO_ROOT),
    )
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    ready = False
    while time.monotonic() < deadline:
        time.sleep(1)
        with contextlib.suppress(Exception):
            if celery_app.control.ping(timeout=1):
                ready = True
                break
    if not ready:
        proc.terminate()
        proc.wait(timeout=10)
        raise RuntimeError("celery worker did not become ready in time")
    try:
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _ensure_real_course() -> tuple[uuid.UUID, str]:
    """Idempotent: creates the real Faculty/Course this project has had
    queued since an earlier session if they don't already exist, reuses
    them otherwise. Returns (course_id, faculty_token)."""
    with session_scope() as session:
        faculty = session.execute(
            select(FacultyORM).where(FacultyORM.name == REAL_FACULTY_NAME)
        ).scalar_one_or_none()
        if faculty is None:
            faculty = FacultyORM(
                id=uuid.uuid4(), name=REAL_FACULTY_NAME, institution=REAL_INSTITUTION, token=uuid.uuid4().hex
            )
            session.add(faculty)
            session.flush()

        course = session.execute(
            select(CourseORM).where(CourseORM.name == REAL_COURSE_NAME)
        ).scalar_one_or_none()
        if course is None:
            discipline = session.execute(
                select(DisciplineORM).where(DisciplineORM.key == "mechanical")
            ).scalar_one()
            course = CourseORM(
                id=uuid.uuid4(),
                name=REAL_COURSE_NAME,
                discipline_id=discipline.id,
                faculty_id=faculty.id,
                faculty_name=faculty.name,
                institution=REAL_INSTITUTION,
            )
            session.add(course)
        elif course.faculty_id is None:
            course.faculty_id = faculty.id

        return course.id, faculty.token


def _watch_sse_until_terminal(
    client: httpx.Client, base_url: str, job_id: str, timeout_s: float
) -> list[dict[str, Any]]:
    """Consumes the real SSE stream, parsing `data:` lines, until a DONE/
    FAILED status is observed or `timeout_s` elapses. Returns every
    distinct payload observed, in order — the actual proof that progress
    was watched live, not just polled once at the end."""
    events: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout_s
    with client.stream(
        "GET", f"{base_url}/api/jobs/{job_id}/stream", timeout=httpx.Timeout(timeout_s, read=timeout_s)
    ) as response:
        assert response.status_code == 200
        data_line: str | None = None
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                break
            if line.startswith("data:"):
                data_line = line[len("data:") :].strip()
            elif line == "" and data_line is not None:
                payload = json.loads(data_line)
                events.append(payload)
                data_line = None
                if payload["status"] in ("done", "failed"):
                    break
    return events


def test_full_upload_to_pdf_run_over_real_http_with_sse(
    live_server: str, celery_worker_process: subprocess.Popen[bytes]
) -> None:
    # Confirm the real book this test's generate half depends on actually
    # exists before spending anything — a clear, honest skip beats a
    # confusing failure deep inside a real LLM call.
    with session_scope() as session:
        big_book = session.get(BookORM, BIG_BOOK_ID)
    if big_book is None:
        pytest.skip(
            f"real book {BIG_BOOK_ID} not present in the dev DB — "
            "this test's generate half depends on earlier sessions' real ingest/S2-S7 run"
        )

    with httpx.Client() as client:
        # --- Part 1: real chunked upload + ingest + SSE, small fixture, no LLM cost ---
        pdf_bytes = (FIXTURES / "sample.pdf").read_bytes()
        init = client.post(
            f"{live_server}/api/books",
            json={"filename": "sample.pdf", "total_bytes": len(pdf_bytes), "discipline": "mechanical"},
        ).json()
        job_id = init["job_id"]

        mid = len(pdf_bytes) // 2
        first = client.patch(
            f"{live_server}/api/books/{job_id}/chunk",
            content=pdf_bytes[:mid],
            headers={"Upload-Offset": "0"},
        )
        assert first.status_code == 200
        second = client.patch(
            f"{live_server}/api/books/{job_id}/chunk",
            content=pdf_bytes[mid:],
            headers={"Upload-Offset": str(mid)},
        )
        assert second.status_code == 200
        assert second.headers["Upload-Offset"] == str(len(pdf_bytes))

        ingest_events = _watch_sse_until_terminal(client, live_server, job_id, JOB_TIMEOUT_S)
        assert ingest_events, "no SSE events observed for the ingest job — the stream never emitted anything"
        assert ingest_events[-1]["status"] == "done", f"ingest job did not finish cleanly: {ingest_events[-1]}"

        book_id = ingest_events[-1]["result_book_id"]
        assert book_id is not None
        with session_scope() as session:
            from practice_forge.db.models import PageORM

            page_count = len(
                session.execute(select(PageORM).where(PageORM.book_id == uuid.UUID(book_id))).scalars().all()
            )
        # Either a fresh extraction (8 real pages) or a real exact-sha256
        # dedup hit reusing a book from a prior run of this same test —
        # both are real outcomes, not a fabricated single expectation.
        assert page_count == 8 or ingest_events[-1]["stage"] == "exact_sha256"

        # --- Part 2: real generate -> S8/S9/S10 -> download, minimal LLM cost ---
        course_id, faculty_token = _ensure_real_course()
        generate_resp = client.post(
            f"{live_server}/api/problem-sets",
            json={"book_id": str(BIG_BOOK_ID), "course_id": str(course_id), "count": 1},
            headers={"Authorization": f"Bearer {faculty_token}"},
        )
        assert generate_resp.status_code == 202, generate_resp.text
        generate_job_id = generate_resp.json()["job_id"]

        generate_events = _watch_sse_until_terminal(client, live_server, generate_job_id, JOB_TIMEOUT_S)
        assert generate_events, "no SSE events observed for the generate job"
        assert any(e["stage"] in ("s7_selection", "s8_s9_generation", "rendering") for e in generate_events), (
            f"never observed an intermediate real stage — got: {[e['stage'] for e in generate_events]}"
        )
        final = generate_events[-1]
        assert final["status"] == "done", f"generate job did not finish cleanly: {final}"

        problem_set_id = final["result_problem_set_id"]
        assert problem_set_id is not None

        detail = client.get(f"{live_server}/api/problem-sets/{problem_set_id}").json()
        assert detail["problem_count"] == 1
        assert len(detail["problems"]) == 1
        assert detail["problems"][0]["verified_answer"] is not None

        handout = client.get(f"{live_server}/api/problem-sets/{problem_set_id}/handout.pdf")
        assert handout.status_code == 200
        assert handout.content.startswith(b"%PDF")
        assert len(handout.content) > 500

        solutions = client.get(f"{live_server}/api/problem-sets/{problem_set_id}/solutions.pdf")
        assert solutions.status_code == 200
        assert solutions.content.startswith(b"%PDF")

        code_zip = client.get(f"{live_server}/api/problem-sets/{problem_set_id}/code.zip")
        assert code_zip.status_code == 200
        assert code_zip.content[:2] == b"PK"  # real zip magic bytes

        with session_scope() as session:
            ledger_rows = session.execute(
                select(IssuedLedgerORM).where(IssuedLedgerORM.problem_set_id == uuid.UUID(problem_set_id))
            ).scalars().all()
        assert len(ledger_rows) == 1, "generate must write exactly one ledger row for the one verified concept"
