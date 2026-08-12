"""Generate / reshuffle / new-set / downloads / chat.

Every generation is a Celery job — this router only ever enqueues and
returns a `job_id` (per spec: "Never block an HTTP request on marker or
on S9"). Reshuffle and new-set are mutually distinct actions, not one
endpoint with a flag (see docs on both routes below and `worker/tasks.py`)
— the ledger side-effect is the load-bearing difference between them.

`/chat` (P12, explain-a-step) is the one exception to "never block": it's
a single short LLM call answering one question, not a bulk pipeline stage
— see `practice_forge.chat.explain_step`'s module docstring.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from practice_forge.chat.explain_step import StepIndexError, explain_step
from practice_forge.db.models import (
    ConceptCardORM,
    ConceptClusterORM,
    CourseORM,
    FacultyORM,
    IssuedLedgerORM,
    JobORM,
    ProblemSetORM,
    VariantORM,
)
from practice_forge.llm.client import LLMClient
from practice_forge.llm.rate_limiter import DailyQuotaExhausted
from practice_forge.models.enums import JobKind, JobStatus
from worker.tasks import generate_task, new_set_task, reshuffle_task

from ..auth import get_current_faculty, require_course_owner
from ..deps import get_db
from ..schemas import (
    ChatRequest,
    GenerateRequest,
    ProblemPreview,
    ProblemSetDetail,
    ProblemSetSummary,
)

router = APIRouter(prefix="/api/problem-sets", tags=["problem-sets"])


class JobAccepted(BaseModel):
    job_id: uuid.UUID


class NewSetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_ids: list[uuid.UUID] | None = None
    count: int | None = None
    difficulty_mix: dict[str, int] | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _book_id_for_problem_set(db: Session, problem_set: ProblemSetORM) -> uuid.UUID:
    variant = db.get(VariantORM, problem_set.variant_ids[0])
    assert variant is not None
    cluster = db.get(ConceptClusterORM, variant.concept_cluster_id)
    assert cluster is not None
    card = db.get(ConceptCardORM, cluster.representative_card_id)
    assert card is not None
    return card.book_id


def _get_problem_set_or_404(db: Session, problem_set_id: uuid.UUID) -> ProblemSetORM:
    problem_set = db.get(ProblemSetORM, problem_set_id)
    if problem_set is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such problem set")
    return problem_set


def _remaining_concepts(db: Session, course_id: uuid.UUID, book_id: uuid.UUID) -> int:
    """How many of the book's real concept clusters are NOT yet issued to
    this course — what "New set" would actually have left to draw from.
    Real counts, not a decorative estimate."""
    total = db.execute(
        select(func.count())
        .select_from(ConceptClusterORM)
        .join(ConceptCardORM, ConceptClusterORM.representative_card_id == ConceptCardORM.id)
        .where(ConceptCardORM.book_id == book_id)
    ).scalar_one()
    issued = db.execute(
        select(func.count(func.distinct(IssuedLedgerORM.concept_cluster_id)))
        .select_from(IssuedLedgerORM)
        .join(ConceptClusterORM, IssuedLedgerORM.concept_cluster_id == ConceptClusterORM.id)
        .join(ConceptCardORM, ConceptClusterORM.representative_card_id == ConceptCardORM.id)
        .where(
            IssuedLedgerORM.course_id == course_id,
            IssuedLedgerORM.is_recycled.is_(False),
            ConceptCardORM.book_id == book_id,
        )
    ).scalar_one()
    return max(total - issued, 0)


def _to_summary(db: Session, problem_set: ProblemSetORM) -> ProblemSetSummary:
    book_id = _book_id_for_problem_set(db, problem_set)
    return ProblemSetSummary(
        id=problem_set.id,
        course_id=problem_set.course_id,
        title=problem_set.title,
        run_number=problem_set.run_number,
        problem_count=len(problem_set.variant_ids),
        created_at=problem_set.created_at,
        remaining_concepts=_remaining_concepts(db, problem_set.course_id, book_id),
    )


@router.post("", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def generate(
    req: GenerateRequest,
    db: Session = Depends(get_db),
    faculty: FacultyORM = Depends(get_current_faculty),
) -> JobAccepted:
    course = db.get(CourseORM, req.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such course")
    require_course_owner(course, faculty)

    job = JobORM(
        id=uuid.uuid4(),
        kind=JobKind.GENERATE,
        status=JobStatus.QUEUED,
        stage="queued",
        book_id=req.book_id,
        course_id=req.course_id,
        params={
            "section_ids": [str(s) for s in (req.section_ids or [])],
            "count": req.count,
            "difficulty_mix": req.difficulty_mix,
        },
        created_by_faculty_id=faculty.id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    generate_task.delay(str(job.id))
    return JobAccepted(job_id=job.id)


@router.get("", response_model=list[ProblemSetSummary])
def list_problem_sets(course_id: uuid.UUID, db: Session = Depends(get_db)) -> list[ProblemSetSummary]:
    problem_sets = db.execute(
        select(ProblemSetORM).where(ProblemSetORM.course_id == course_id).order_by(ProblemSetORM.run_number)
    ).scalars().all()
    return [_to_summary(db, p) for p in problem_sets]


@router.get("/{problem_set_id}", response_model=ProblemSetDetail)
def get_problem_set(problem_set_id: uuid.UUID, db: Session = Depends(get_db)) -> ProblemSetDetail:
    problem_set = _get_problem_set_or_404(db, problem_set_id)
    previews: list[ProblemPreview] = []
    for i, variant_id in enumerate(problem_set.variant_ids, start=1):
        variant = db.get(VariantORM, variant_id)
        assert variant is not None
        cluster = db.get(ConceptClusterORM, variant.concept_cluster_id)
        assert cluster is not None
        card = db.get(ConceptCardORM, cluster.representative_card_id)
        assert card is not None
        previews.append(
            ProblemPreview(
                index=i,
                name=card.name,
                statement_md=variant.statement_md,
                difficulty=variant.difficulty.value,
                solution_steps=variant.solution_steps,
                core_python_code=variant.core_python_code,
                verified_answer=variant.verified_answer,
                extension_type=variant.extension_type.value,
            )
        )
    summary = _to_summary(db, problem_set)
    return ProblemSetDetail(**summary.model_dump(), problems=previews)


@router.post("/{problem_set_id}/reshuffle", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def reshuffle(
    problem_set_id: uuid.UUID,
    db: Session = Depends(get_db),
    faculty: FacultyORM = Depends(get_current_faculty),
) -> JobAccepted:
    """Same clusters, fresh params — does NOT touch IssuedLedger. Unlimited:
    a course can reshuffle the same set as many times as it wants."""
    original = _get_problem_set_or_404(db, problem_set_id)
    course = db.get(CourseORM, original.course_id)
    assert course is not None
    require_course_owner(course, faculty)

    job = JobORM(
        id=uuid.uuid4(),
        kind=JobKind.RESHUFFLE,
        status=JobStatus.QUEUED,
        stage="queued",
        book_id=_book_id_for_problem_set(db, original),
        course_id=original.course_id,
        params={"original_problem_set_id": str(original.id)},
        created_by_faculty_id=faculty.id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    reshuffle_task.delay(str(job.id))
    return JobAccepted(job_id=job.id)


@router.post("/{problem_set_id}/new-set", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED)
def new_set(
    problem_set_id: uuid.UUID,
    req: NewSetRequest,
    db: Session = Depends(get_db),
    faculty: FacultyORM = Depends(get_current_faculty),
) -> JobAccepted:
    """20 DIFFERENT topics — a fresh S7 selection that excludes every
    cluster already in this course's ledger, permanently consuming that
    many more of the book's concepts. Defaults to the same book/course/
    section scope the original set was generated with (recovered from that
    set's own generating job), overridable via the request body."""
    original = _get_problem_set_or_404(db, problem_set_id)
    course = db.get(CourseORM, original.course_id)
    assert course is not None
    require_course_owner(course, faculty)

    original_job = db.execute(
        select(JobORM).where(JobORM.result_problem_set_id == original.id)
    ).scalar_one_or_none()
    original_params = (original_job.params if original_job else None) or {}

    section_ids = req.section_ids if req.section_ids is not None else original_params.get("section_ids")
    count = req.count if req.count is not None else original_params.get("count", len(original.variant_ids))
    difficulty_mix = (
        req.difficulty_mix if req.difficulty_mix is not None else original_params.get("difficulty_mix")
    )

    job = JobORM(
        id=uuid.uuid4(),
        kind=JobKind.NEW_SET,
        status=JobStatus.QUEUED,
        stage="queued",
        book_id=_book_id_for_problem_set(db, original),
        course_id=original.course_id,
        params={
            "section_ids": [str(s) for s in (section_ids or [])],
            "count": count,
            "difficulty_mix": difficulty_mix,
        },
        created_by_faculty_id=faculty.id,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(job)
    db.commit()
    new_set_task.delay(str(job.id))
    return JobAccepted(job_id=job.id)


@router.get("/{problem_set_id}/handout.pdf")
def download_handout(problem_set_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    problem_set = _get_problem_set_or_404(db, problem_set_id)
    return FileResponse(
        problem_set.student_pdf_path, media_type="application/pdf", filename="handout.pdf"
    )


@router.get("/{problem_set_id}/solutions.pdf")
def download_solutions(problem_set_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    problem_set = _get_problem_set_or_404(db, problem_set_id)
    return FileResponse(
        problem_set.solutions_pdf_path, media_type="application/pdf", filename="solutions.pdf"
    )


@router.get("/{problem_set_id}/code.zip")
def download_code_zip(problem_set_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    problem_set = _get_problem_set_or_404(db, problem_set_id)
    code_dir = Path(problem_set.student_pdf_path).parent / "code"
    if not code_dir.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No code folder for this problem set")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for py_file in sorted(code_dir.glob("*.py")):
            zf.write(py_file, arcname=py_file.name)
    buffer.seek(0)
    return Response(
        buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=code.zip"},
    )


@router.post("/{problem_set_id}/chat")
def chat(
    problem_set_id: uuid.UUID, req: ChatRequest, db: Session = Depends(get_db)
) -> dict[str, str]:
    """P12: real per-step Q&A -- one synchronous LLM call, see this
    router's module docstring for why blocking here is fine."""
    problem_set = _get_problem_set_or_404(db, problem_set_id)
    if not (1 <= req.problem_index <= len(problem_set.variant_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No problem at index {req.problem_index}")
    variant = db.get(VariantORM, problem_set.variant_ids[req.problem_index - 1])
    assert variant is not None

    try:
        answer = explain_step(
            LLMClient(), f"chat-{problem_set_id}-{req.problem_index}", variant, req.step_index, req.question
        )
    except StepIndexError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except DailyQuotaExhausted as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return {"answer": answer}
