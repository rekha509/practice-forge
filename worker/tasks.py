"""Real Celery tasks (P10): every long operation the API exposes runs
here, never inline in an HTTP request handler (per the product spec: "Never
block an HTTP request on marker or on S9"). Each task loads its own
`JobORM` row for progress reporting — `GET /api/jobs/{id}/stream` (P10)
polls that row, not Celery's own result backend, so progress survives
independently of whether the requesting client is even still connected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from practice_forge.codegen.codegen import generate_and_verify_solution
from practice_forge.config import REPO_ROOT
from practice_forge.db.base import session_scope
from practice_forge.db.models import (
    BookORM,
    ConceptCardORM,
    ConceptClusterORM,
    CourseORM,
    DisciplineORM,
    IssuedLedgerORM,
    JobORM,
    ProblemSetORM,
    SourceProblemORM,
    VariantORM,
)
from practice_forge.ingest.pipeline import run_ingest_resumable
from practice_forge.llm.client import LLMClient
from practice_forge.models.enums import ExtensionType, JobStatus, VerificationStatus
from practice_forge.profiles.loader import load_profile
from practice_forge.render.render import render_variant_ids
from practice_forge.selection.selection import run_selection
from practice_forge.variants.variants import generate_variant, select_extension_attachments

from .celery_app import celery_app

GENERATED_SETS_DIR = REPO_ROOT / "data" / "generated"

_STANDARD_LIBS = {"pint", "numpy", "sympy", "scipy", "matplotlib"}


def _now() -> datetime:
    return datetime.now(UTC)


def _fail_job(job: JobORM, message: str) -> None:
    job.status = JobStatus.FAILED
    job.error_message = message
    job.updated_at = _now()


# ---------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------


@celery_app.task(name="worker.tasks.ingest_task")  # type: ignore[untyped-decorator]
def ingest_task(job_id: str) -> None:
    with session_scope() as session:
        job = session.get(JobORM, uuid.UUID(job_id))
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.stage = "extracting"
        job.extraction_started_at = _now()
        job.updated_at = _now()
        session.commit()

        assert job.upload_path is not None
        assert job.discipline_key is not None

        def on_progress(done: int, total: int) -> None:
            job.pages_done = done
            job.pages_total = total
            job.updated_at = _now()
            session.commit()

        try:
            result = run_ingest_resumable(
                session,
                Path(job.upload_path),
                discipline_key=job.discipline_key,
                uploaded_by=str(job.created_by_faculty_id or "api"),
                progress_cb=on_progress,
                llm_client=LLMClient(),
            )
        except Exception as exc:
            _fail_job(job, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise

        job.status = JobStatus.DONE
        job.stage = result.dedup_hit or "extracted"
        job.book_id = result.book_id
        job.updated_at = _now()
        session.commit()


# ---------------------------------------------------------------------
# Generate / new-set / reshuffle — shared core
# ---------------------------------------------------------------------


@dataclass(frozen=True)
class _GenTarget:
    """The minimum `_generate_variants_for_selection` needs per item —
    deliberately NOT `selection.PoolMember` (which requires a real
    `CandidateScore`, meaningless for a reshuffle, which regenerates
    variants for already-selected clusters without re-scoring anything)."""

    cluster_id: uuid.UUID
    card: ConceptCardORM
    difficulty_tier: str


def _next_run_number(session: Session, course_id: uuid.UUID) -> int:
    existing = (
        session.execute(select(ProblemSetORM.run_number).where(ProblemSetORM.course_id == course_id))
        .scalars()
        .all()
    )
    return (max(existing) + 1) if existing else 1


def _generate_variants(
    session: Session,
    job: JobORM,
    *,
    targets: list[_GenTarget],
    attachments: dict[uuid.UUID, ExtensionType | None],
    client: LLMClient,
    sandbox_image: str,
    extra_libs: list[str],
) -> list[uuid.UUID]:
    """S8 (variant) + S9 (codegen/verify) for each target, one commit per
    item — a single bad generation must not lose already-paid-for LLM work
    for the rest of the set (the same commit-per-item discipline S3/S5/S6
    already use). Returns VERIFIED variant ids, in target order; a target
    whose generation/verification failed is silently excluded from the
    final set (not padded, not retried indefinitely) — its concept is NOT
    considered issued (callers must not write a ledger row for it)."""
    job.items_total = len(targets)
    job.items_done = 0
    session.commit()

    variant_ids: list[uuid.UUID] = []
    for i, target in enumerate(targets):
        problem = session.get(SourceProblemORM, target.card.source_problem_id)
        assert problem is not None

        variant = generate_variant(
            client, f"{job.id}-s8-{i}", target.cluster_id, target.card, problem, target.difficulty_tier
        )
        if variant is not None:
            extension = attachments.get(target.card.id)
            if extension is not None:
                variant.extension_type = extension
            generate_and_verify_solution(
                client,
                f"{job.id}-s9-{i}",
                target.card,
                variant,
                extra_libs=extra_libs,
                sandbox_image=sandbox_image,
                sandbox_timeout_s=15,
            )
            if variant.verification_status == VerificationStatus.VERIFIED:
                session.add(variant)
                variant_ids.append(variant.id)

        job.items_done = i + 1
        job.updated_at = _now()
        session.commit()

    return variant_ids


def _render_and_persist_problem_set(
    session: Session,
    *,
    book_id: uuid.UUID,
    course_id: uuid.UUID,
    variant_ids: list[uuid.UUID],
) -> ProblemSetORM:
    course = session.get(CourseORM, course_id)
    assert course is not None
    run_number = _next_run_number(session, course_id)
    title = f"{course.name} — Set {run_number}"
    out_dir = GENERATED_SETS_DIR / str(book_id) / "sets" / str(uuid.uuid4())

    result = render_variant_ids(session, variant_ids, out_dir, title)
    typst_source = (out_dir / "student_handout.typ").read_text(encoding="utf-8")

    problem_set = ProblemSetORM(
        id=uuid.uuid4(),
        course_id=course_id,
        title=title,
        run_number=run_number,
        variant_ids=variant_ids,
        typst_source=typst_source,
        student_pdf_path=result.student_pdf_path,
        solutions_pdf_path=result.solutions_pdf_path,
        created_at=_now(),
    )
    session.add(problem_set)
    session.commit()
    return problem_set


def _write_ledger(session: Session, *, course_id: uuid.UUID, problem_set: ProblemSetORM) -> None:
    """One row per `problem_set.variant_ids` entry -- confirmed correct for
    that (real, live-tested): a target that failed S8/S9 is never in
    `variant_ids` to begin with (see `_generate_variants`'s own docstring),
    so a smaller-than-requested set here means fewer targets succeeded, not
    a dropped ledger write.

    `is_recycled` WAS hardcoded False here, contradicting IssuedLedgerORM's
    own docstring ("Denormalized from Variant.is_recycled at write time") --
    currently harmless since nothing in this codebase ever sets
    Variant.is_recycled True yet, but real drift from the documented
    contract nonetheless. Reads the real value off each variant instead."""
    now = _now()
    for variant_id in problem_set.variant_ids:
        variant = session.get(VariantORM, variant_id)
        assert variant is not None
        session.add(
            IssuedLedgerORM(
                id=uuid.uuid4(),
                course_id=course_id,
                concept_cluster_id=variant.concept_cluster_id,
                variant_id=variant_id,
                problem_set_id=problem_set.id,
                issued_at=now,
                is_recycled=variant.is_recycled,
            )
        )
    session.commit()


def _sandbox_context(session: Session, book_id: uuid.UUID) -> tuple[str, list[str]]:
    book = session.get(BookORM, book_id)
    assert book is not None
    discipline = session.get(DisciplineORM, book.discipline_id)
    assert discipline is not None
    profile = load_profile(discipline.key)
    extra_libs = [lib for lib in profile.solver_libs if lib not in _STANDARD_LIBS]
    return discipline.sandbox_image_tag, extra_libs


@celery_app.task(name="worker.tasks.generate_task")  # type: ignore[untyped-decorator]
def generate_task(job_id: str) -> None:
    """Backs both `POST /api/problem-sets` (first generation for a course)
    and `POST /api/problem-sets/{id}/new-set` — both run a FRESH S7
    selection that excludes every cluster already in this course's ledger,
    and both write new ledger rows for whatever verifies. The API router
    is what fills in `job.params` differently for the two cases (new-set
    resolves book/course/section defaults from the original set's own
    generating job); this task doesn't need to know which endpoint
    triggered it."""
    with session_scope() as session:
        job = session.get(JobORM, uuid.UUID(job_id))
        if job is None:
            return
        assert job.book_id is not None
        assert job.course_id is not None
        params = job.params or {}
        raw_section_ids = params.get("section_ids") or []
        section_ids = frozenset(uuid.UUID(s) for s in raw_section_ids)
        count = params.get("count", 20)
        difficulty_mix = params.get("difficulty_mix")

        job.status = JobStatus.RUNNING
        job.stage = "s7_selection"
        job.updated_at = _now()
        session.commit()

        try:
            already_issued = frozenset(
                session.execute(
                    select(IssuedLedgerORM.concept_cluster_id).where(
                        IssuedLedgerORM.course_id == job.course_id,
                        IssuedLedgerORM.is_recycled.is_(False),
                    )
                )
                .scalars()
                .all()
            )
            selection_result = run_selection(
                session,
                job.book_id,
                excluded_cluster_ids=already_issued,
                section_ids=section_ids or None,
                target_set_size=count,
                difficulty_mix=difficulty_mix,
            )
            if not selection_result.can_reach_target:
                _fail_job(job, f"cannot reach target: {selection_result.reason}")
                session.commit()
                return

            sandbox_image, extra_libs = _sandbox_context(session, job.book_id)
            client = LLMClient()
            job.stage = "s8_s9_generation"
            session.commit()

            attachments = select_extension_attachments(selection_result.selected)
            targets = [
                _GenTarget(cluster_id=m.cluster_id, card=m.card, difficulty_tier=m.difficulty_tier)
                for m in selection_result.selected
            ]
            variant_ids = _generate_variants(
                session,
                job,
                targets=targets,
                attachments=attachments,
                client=client,
                sandbox_image=sandbox_image,
                extra_libs=extra_libs,
            )
            if not variant_ids:
                _fail_job(job, "every generated variant failed S9 verification")
                session.commit()
                return

            job.stage = "rendering"
            session.commit()
            problem_set = _render_and_persist_problem_set(
                session, book_id=job.book_id, course_id=job.course_id, variant_ids=variant_ids
            )
            _write_ledger(session, course_id=job.course_id, problem_set=problem_set)

            job.status = JobStatus.DONE
            job.stage = "done"
            job.result_problem_set_id = problem_set.id
            job.updated_at = _now()
            session.commit()
        except Exception as exc:
            _fail_job(job, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise


@celery_app.task(name="worker.tasks.new_set_task")  # type: ignore[untyped-decorator]
def new_set_task(job_id: str) -> None:
    """`new-set`'s API router resolves `job.params` (book/course/section/
    count/difficulty_mix) before enqueueing, defaulting to the original
    problem set's own generating job's params unless overridden — from
    there this is mechanically identical to `generate_task` (fresh
    selection excluding every already-issued cluster, S8/S9, render,
    ledger write)."""
    generate_task(job_id)


@celery_app.task(name="worker.tasks.reshuffle_task")  # type: ignore[untyped-decorator]
def reshuffle_task(job_id: str) -> None:
    """Same clusters as an existing ProblemSet (each one's extension
    attachment carried over unchanged, not re-decided), fresh S8/S9
    output — never touches IssuedLedger. The clusters are already
    recorded there from whenever they were first issued; reshuffling
    doesn't issue anything new."""
    with session_scope() as session:
        job = session.get(JobORM, uuid.UUID(job_id))
        if job is None:
            return
        params = job.params or {}
        original_problem_set_id = uuid.UUID(params["original_problem_set_id"])

        job.status = JobStatus.RUNNING
        job.stage = "s8_s9_generation"
        job.updated_at = _now()
        session.commit()

        try:
            original = session.get(ProblemSetORM, original_problem_set_id)
            assert original is not None
            assert job.book_id is not None

            targets: list[_GenTarget] = []
            attachments: dict[uuid.UUID, ExtensionType | None] = {}
            for variant_id in original.variant_ids:
                old_variant = session.get(VariantORM, variant_id)
                assert old_variant is not None
                cluster = session.get(ConceptClusterORM, old_variant.concept_cluster_id)
                assert cluster is not None
                card = session.get(ConceptCardORM, cluster.representative_card_id)
                assert card is not None
                targets.append(
                    _GenTarget(
                        cluster_id=cluster.id, card=card, difficulty_tier=old_variant.difficulty.value
                    )
                )
                attachments[card.id] = (
                    old_variant.extension_type if old_variant.extension_type != ExtensionType.NONE else None
                )

            sandbox_image, extra_libs = _sandbox_context(session, job.book_id)
            client = LLMClient()
            variant_ids = _generate_variants(
                session,
                job,
                targets=targets,
                attachments=attachments,
                client=client,
                sandbox_image=sandbox_image,
                extra_libs=extra_libs,
            )
            if not variant_ids:
                _fail_job(job, "every reshuffled variant failed S9 verification")
                session.commit()
                return

            job.stage = "rendering"
            session.commit()
            problem_set = _render_and_persist_problem_set(
                session, book_id=job.book_id, course_id=original.course_id, variant_ids=variant_ids
            )
            # Deliberately no _write_ledger call — reshuffle never touches
            # IssuedLedger (see docstring).

            job.status = JobStatus.DONE
            job.stage = "done"
            job.result_problem_set_id = problem_set.id
            job.updated_at = _now()
            session.commit()
        except Exception as exc:
            _fail_job(job, f"{type(exc).__name__}: {exc}")
            session.commit()
            raise
