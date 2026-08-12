"""P10 API tests — Tier A: fast, isolated to the test DB, every Celery
task's `.delay()` monkeypatched to a no-op recorder. These prove the
ROUTER layer (auth, ownership checks, request validation, job creation,
param serialization, download plumbing) without ever touching a real
Celery worker, real Gemini call, or real sandbox — that's what the
separate, explicitly-run, `@pytest.mark.llm` end-to-end test in
test_api_e2e.py is for (see its own module docstring for why it's kept
out of the routine, always-run suite: real LLM quota, a real subprocess
Celery worker, a real Docker sandbox).

`db_session` (tests/conftest.py) IS the database this whole test module
talks to — `get_db` is overridden to yield it directly, so router code
and test assertions share one transaction, and the DB is truncated fresh
per test (including P10's own tables — see conftest.py's edited
truncation list).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from api.main import app
from practice_forge.db.models import (
    BookORM,
    CandidateScoreORM,
    ConceptCardORM,
    ConceptClusterORM,
    CourseORM,
    DisciplineORM,
    FacultyORM,
    IssuedLedgerORM,
    JobORM,
    ProblemSetORM,
    SectionORM,
    SourceProblemORM,
    VariantORM,
)
from practice_forge.models.enums import (
    DifficultyLevel,
    ExtensionType,
    JobKind,
    JobStatus,
    ProblemKind,
    VerificationStatus,
)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _now() -> datetime:
    return datetime.now(UTC)


def _make_faculty(db: Session, name: str = "Mahesh", token: str | None = None) -> FacultyORM:
    faculty = FacultyORM(
        id=uuid.uuid4(), name=name, institution="RGUKT Basar", token=token or uuid.uuid4().hex
    )
    db.add(faculty)
    db.commit()
    return faculty


def _make_course(db: Session, faculty: FacultyORM | None) -> CourseORM:
    discipline = db.execute(select(DisciplineORM).where(DisciplineORM.key == "mechanical")).scalar_one()
    course = CourseORM(
        id=uuid.uuid4(),
        name="AI/ML for Mechanical Systems",
        discipline_id=discipline.id,
        faculty_id=faculty.id if faculty else None,
        faculty_name=faculty.name if faculty else "Unclaimed",
        institution="RGUKT Basar",
    )
    db.add(course)
    db.commit()
    return course


def _make_book_with_cluster(db: Session) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Returns (book_id, section_id, cluster_id) for a single real concept
    card + cluster, matching the FK shape every real S1-S7 row needs."""
    discipline = db.execute(select(DisciplineORM).where(DisciplineORM.key == "mechanical")).scalar_one()
    book = BookORM(
        id=uuid.uuid4(),
        title="API Test Book",
        authors=[],
        discipline_id=discipline.id,
        page_count=10,
        file_sha256=uuid.uuid4().hex,
        uploaded_by="test",
    )
    db.add(book)
    db.flush()
    section = SectionORM(
        id=uuid.uuid4(), book_id=book.id, chapter_no=1, title="Ch1", page_start=1, page_end=10
    )
    db.add(section)
    db.flush()
    problem = SourceProblemORM(
        id=uuid.uuid4(),
        book_id=book.id,
        section_id=section.id,
        page_no=1,
        kind=ProblemKind.WORKED_EXAMPLE,
        statement_md="A problem.",
        is_solvable=True,
    )
    db.add(problem)
    db.flush()
    embedding = [0.0] * 3072
    embedding[0] = 1.0
    card = ConceptCardORM(
        id=uuid.uuid4(),
        book_id=book.id,
        section_id=section.id,
        source_problem_id=problem.id,
        name="concept-1",
        topic_node_ids=[],
        governing_equations_latex=["E = m c^2"],
        canonical_equation_srepr=["UNPARSED::E = m c^2"],
        solution_strategy="solve",
        given_dimensions=["mass"],
        solve_for_dimension="energy",
        method_tag="method-1",
        concept_fingerprint="fp-1",
        embedding=embedding,
        source_pages=[1],
    )
    db.add(card)
    db.flush()
    db.add(
        CandidateScoreORM(
            id=uuid.uuid4(),
            concept_card_id=card.id,
            pedagogical_value=0.5,
            computational_suitability=5,
            self_containedness=0.5,
            syllabus_centrality=0.5,
            verifiability=0.5,
            ml_extension_potential=0.5,
            difficulty=DifficultyLevel.MEDIUM,
            eligible_extension_types=["surrogate_model"],
            composite_score=0.5,
            scoring_rationale={},
        )
    )
    cluster = ConceptClusterORM(
        id=uuid.uuid4(),
        discipline_id=discipline.id,
        representative_card_id=card.id,
        member_card_ids=[card.id],
        centroid_embedding=embedding,
    )
    db.add(cluster)
    db.commit()
    return book.id, section.id, cluster.id


def _add_extra_cluster(db: Session, book_id: uuid.UUID, section_id: uuid.UUID) -> uuid.UUID:
    """A second real concept card + cluster in an ALREADY-existing book/
    section — for tests that need more than one cluster to draw on
    (e.g. remaining_concepts, which is meaningless with a pool of 1)."""
    book = db.get(BookORM, book_id)
    assert book is not None
    problem = SourceProblemORM(
        id=uuid.uuid4(),
        book_id=book_id,
        section_id=section_id,
        page_no=2,
        kind=ProblemKind.WORKED_EXAMPLE,
        statement_md="A second problem.",
        is_solvable=True,
    )
    db.add(problem)
    db.flush()
    embedding = [0.0] * 3072
    embedding[1] = 1.0
    card = ConceptCardORM(
        id=uuid.uuid4(),
        book_id=book_id,
        section_id=section_id,
        source_problem_id=problem.id,
        name="concept-2",
        topic_node_ids=[],
        governing_equations_latex=["F = m a"],
        canonical_equation_srepr=["UNPARSED::F = m a"],
        solution_strategy="solve",
        given_dimensions=["mass"],
        solve_for_dimension="force",
        method_tag="method-2",
        concept_fingerprint="fp-2",
        embedding=embedding,
        source_pages=[2],
    )
    db.add(card)
    db.flush()
    db.add(
        CandidateScoreORM(
            id=uuid.uuid4(),
            concept_card_id=card.id,
            pedagogical_value=0.5,
            computational_suitability=5,
            self_containedness=0.5,
            syllabus_centrality=0.5,
            verifiability=0.5,
            ml_extension_potential=0.5,
            difficulty=DifficultyLevel.MEDIUM,
            eligible_extension_types=["surrogate_model"],
            composite_score=0.5,
            scoring_rationale={},
        )
    )
    cluster = ConceptClusterORM(
        id=uuid.uuid4(),
        discipline_id=book.discipline_id,
        representative_card_id=card.id,
        member_card_ids=[card.id],
        centroid_embedding=embedding,
    )
    db.add(cluster)
    db.commit()
    return cluster.id


def _make_variant(db: Session, cluster_id: uuid.UUID, *, verified: bool = True) -> VariantORM:
    variant = VariantORM(
        id=uuid.uuid4(),
        concept_cluster_id=cluster_id,
        statement_md="A rewritten problem.",
        params={"x": 1.0},
        difficulty=DifficultyLevel.MEDIUM,
        topic_node_ids=[],
        solution_steps=["Step one."],
        core_python_code="print('RESULT x: 1.0')",
        extension_type=ExtensionType.NONE,
        extension_python_code=None,
        extension_learning_notes=None,
        extension_figure_paths=[],
        extension_metrics_json=None,
        verified_answer="{'x': 1.0}",
        verification_status=VerificationStatus.VERIFIED if verified else VerificationStatus.FAILED,
        verification_log=[],
        needs_review=False,
        source_ref={},
        is_recycled=False,
    )
    db.add(variant)
    db.commit()
    return variant


def _make_rendered_problem_set(
    db: Session, course_id: uuid.UUID, variant_ids: list[uuid.UUID], tmp_path: Path
) -> ProblemSetORM:
    out_dir = tmp_path / "rendered"
    code_dir = out_dir / "code"
    code_dir.mkdir(parents=True)
    (out_dir / "student_handout.pdf").write_bytes(b"%PDF-1.4 fake handout")
    (out_dir / "solutions_manual.pdf").write_bytes(b"%PDF-1.4 fake solutions")
    (code_dir / "problem_01.py").write_text("print('hi')", encoding="utf-8")

    problem_set = ProblemSetORM(
        id=uuid.uuid4(),
        course_id=course_id,
        title="Test Set",
        run_number=1,
        variant_ids=variant_ids,
        typst_source="#set page()",
        student_pdf_path=str(out_dir / "student_handout.pdf"),
        solutions_pdf_path=str(out_dir / "solutions_manual.pdf"),
        created_at=_now(),
    )
    db.add(problem_set)
    db.commit()
    return problem_set


# ---------------------------------------------------------------------
# Auth / ownership
# ---------------------------------------------------------------------


def test_generate_requires_auth(client: TestClient) -> None:
    # 401 fires from the auth dependency itself, before the course/book
    # are even looked up — neither needs to exist for this assertion.
    resp = client.post(
        "/api/problem-sets",
        json={"book_id": str(uuid.uuid4()), "course_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


def test_generate_rejects_wrong_faculty(client: TestClient, db_session: Session) -> None:
    owner = _make_faculty(db_session, "Owner")
    intruder = _make_faculty(db_session, "Intruder")
    course = _make_course(db_session, faculty=owner)
    book_id, _, _ = _make_book_with_cluster(db_session)

    resp = client.post(
        "/api/problem-sets",
        json={"book_id": str(book_id), "course_id": str(course.id)},
        headers={"Authorization": f"Bearer {intruder.token}"},
    )
    assert resp.status_code == 403


def test_generate_allows_owner(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    faculty = _make_faculty(db_session)
    course = _make_course(db_session, faculty=faculty)
    book_id, section_id, _ = _make_book_with_cluster(db_session)

    calls: list[str] = []
    monkeypatch.setattr("api.routers.problem_sets.generate_task.delay", lambda job_id: calls.append(job_id))

    resp = client.post(
        "/api/problem-sets",
        json={
            "book_id": str(book_id),
            "course_id": str(course.id),
            "section_ids": [str(section_id)],
            "count": 5,
        },
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert calls == [job_id]

    job = db_session.get(JobORM, uuid.UUID(job_id))
    assert job is not None
    assert job.kind == JobKind.GENERATE
    assert job.book_id == book_id
    assert job.course_id == course.id
    assert job.params == {"section_ids": [str(section_id)], "count": 5, "difficulty_mix": None}


def test_generate_rejects_unknown_fields(client: TestClient, db_session: Session) -> None:
    faculty = _make_faculty(db_session)
    course = _make_course(db_session, faculty=faculty)
    resp = client.post(
        "/api/problem-sets",
        json={"book_id": str(uuid.uuid4()), "course_id": str(course.id), "bogus_field": 1},
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 422


def test_generate_404s_on_unknown_course(client: TestClient, db_session: Session) -> None:
    faculty = _make_faculty(db_session)
    resp = client.post(
        "/api/problem-sets",
        json={"book_id": str(uuid.uuid4()), "course_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------


def test_list_books_reports_real_concept_count(client: TestClient, db_session: Session) -> None:
    book_id, _, _ = _make_book_with_cluster(db_session)
    resp = client.get("/api/books")
    assert resp.status_code == 200
    books = {b["id"]: b for b in resp.json()}
    assert str(book_id) in books
    assert books[str(book_id)]["concept_count"] == 1
    assert books[str(book_id)]["page_count"] == 10


def test_get_book_detail_reports_per_section_counts(client: TestClient, db_session: Session) -> None:
    book_id, section_id, _ = _make_book_with_cluster(db_session)
    resp = client.get(f"/api/books/{book_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(book_id)
    assert len(body["sections"]) == 1
    assert body["sections"][0]["id"] == str(section_id)
    assert body["sections"][0]["problem_count"] == 1


def test_get_book_404s_on_unknown_id(client: TestClient) -> None:
    resp = client.get(f"/api/books/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Chunked upload
# ---------------------------------------------------------------------


def test_initiate_upload_creates_uploading_job(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/api/books", json={"filename": "book.pdf", "total_bytes": 20, "discipline": "mechanical"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    job = db_session.get(JobORM, uuid.UUID(body["job_id"]))
    assert job is not None
    assert job.kind == JobKind.INGEST
    assert job.status == JobStatus.UPLOADING
    assert job.bytes_total == 20
    assert job.bytes_received == 0
    assert job.upload_path is not None
    assert Path(job.upload_path).exists()


def test_upload_chunk_head_reports_real_offset(client: TestClient, db_session: Session) -> None:
    init = client.post(
        "/api/books", json={"filename": "book.pdf", "total_bytes": 10, "discipline": "mechanical"}
    ).json()
    resp = client.head(f"/api/books/{init['job_id']}/chunk")
    assert resp.headers["Upload-Offset"] == "0"


def test_upload_chunk_rejects_stale_offset(client: TestClient, db_session: Session) -> None:
    init = client.post(
        "/api/books", json={"filename": "book.pdf", "total_bytes": 10, "discipline": "mechanical"}
    ).json()
    resp = client.patch(
        f"/api/books/{init['job_id']}/chunk",
        content=b"12345",
        headers={"Upload-Offset": "3"},  # client thinks 3 bytes already landed; none have
    )
    assert resp.status_code == 409


def test_upload_chunk_resumes_from_real_offset_across_two_patches(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("api.routers.books.ingest_task.delay", lambda job_id: None)
    total = 10
    init = client.post(
        "/api/books", json={"filename": "book.pdf", "total_bytes": total, "discipline": "mechanical"}
    ).json()
    job_id = init["job_id"]

    first = client.patch(
        f"/api/books/{job_id}/chunk", content=b"AAAAA", headers={"Upload-Offset": "0"}
    )
    assert first.status_code == 200
    assert first.headers["Upload-Offset"] == "5"

    # Simulate the client re-HEADing after a dropped connection before resuming.
    head = client.head(f"/api/books/{job_id}/chunk")
    assert head.headers["Upload-Offset"] == "5"

    second = client.patch(
        f"/api/books/{job_id}/chunk", content=b"BBBBB", headers={"Upload-Offset": "5"}
    )
    assert second.status_code == 200
    assert second.headers["Upload-Offset"] == "10"

    job = db_session.get(JobORM, uuid.UUID(job_id))
    assert job is not None
    assert job.status == JobStatus.QUEUED
    assert job.upload_path is not None
    assert Path(job.upload_path).read_bytes() == b"AAAAABBBBB"


def test_upload_chunk_completing_enqueues_ingest(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("api.routers.books.ingest_task.delay", lambda job_id: calls.append(job_id))
    init = client.post(
        "/api/books", json={"filename": "book.pdf", "total_bytes": 4, "discipline": "mechanical"}
    ).json()
    resp = client.patch(f"/api/books/{init['job_id']}/chunk", content=b"data", headers={"Upload-Offset": "0"})
    assert resp.status_code == 200
    assert calls == [init["job_id"]]


# ---------------------------------------------------------------------
# Reshuffle / new-set
# ---------------------------------------------------------------------


def test_reshuffle_enqueues_without_touching_ledger_params(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    faculty = _make_faculty(db_session)
    course = _make_course(db_session, faculty=faculty)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    calls: list[str] = []
    monkeypatch.setattr("api.routers.problem_sets.reshuffle_task.delay", lambda job_id: calls.append(job_id))

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/reshuffle",
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    assert calls == [job_id]

    job = db_session.get(JobORM, uuid.UUID(job_id))
    assert job is not None
    assert job.kind == JobKind.RESHUFFLE
    assert job.params == {"original_problem_set_id": str(problem_set.id)}


def test_reshuffle_requires_ownership(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    owner = _make_faculty(db_session, "Owner")
    intruder = _make_faculty(db_session, "Intruder")
    course = _make_course(db_session, faculty=owner)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/reshuffle",
        headers={"Authorization": f"Bearer {intruder.token}"},
    )
    assert resp.status_code == 403


def test_new_set_defaults_params_from_original_generating_job(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    faculty = _make_faculty(db_session)
    course = _make_course(db_session, faculty=faculty)
    book_id, section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    original_job = JobORM(
        id=uuid.uuid4(),
        kind=JobKind.GENERATE,
        status=JobStatus.DONE,
        stage="done",
        book_id=book_id,
        course_id=course.id,
        params={"section_ids": [str(section_id)], "count": 7, "difficulty_mix": None},
        result_problem_set_id=problem_set.id,
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(original_job)
    db_session.commit()

    calls: list[str] = []
    monkeypatch.setattr("api.routers.problem_sets.new_set_task.delay", lambda job_id: calls.append(job_id))

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/new-set",
        json={},
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 202, resp.text
    new_job = db_session.get(JobORM, uuid.UUID(resp.json()["job_id"]))
    assert new_job is not None
    assert new_job.kind == JobKind.NEW_SET
    assert new_job.params == {"section_ids": [str(section_id)], "count": 7, "difficulty_mix": None}


def test_new_set_override_replaces_original_params(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    faculty = _make_faculty(db_session)
    course = _make_course(db_session, faculty=faculty)
    book_id, section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)
    db_session.add(
        JobORM(
            id=uuid.uuid4(),
            kind=JobKind.GENERATE,
            status=JobStatus.DONE,
            stage="done",
            book_id=book_id,
            course_id=course.id,
            params={"section_ids": [str(section_id)], "count": 7, "difficulty_mix": None},
            result_problem_set_id=problem_set.id,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db_session.commit()
    monkeypatch.setattr("api.routers.problem_sets.new_set_task.delay", lambda job_id: None)

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/new-set",
        json={"count": 15},
        headers={"Authorization": f"Bearer {faculty.token}"},
    )
    assert resp.status_code == 202, resp.text
    new_job = db_session.get(JobORM, uuid.UUID(resp.json()["job_id"]))
    assert new_job is not None
    assert new_job.params is not None
    assert new_job.params["count"] == 15
    assert new_job.params["section_ids"] == [str(section_id)]  # unspecified -> inherited


# ---------------------------------------------------------------------
# Detail / downloads / chat stub
# ---------------------------------------------------------------------


def test_get_problem_set_detail_includes_preview(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    resp = client.get(f"/api/problem-sets/{problem_set.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_count"] == 1
    assert len(body["problems"]) == 1
    assert body["problems"][0]["statement_md"] == variant.statement_md
    assert body["problems"][0]["verified_answer"] == variant.verified_answer
    assert body["problems"][0]["core_python_code"] == variant.core_python_code


def test_remaining_concepts_counts_unissued_clusters_for_the_course(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    course = _make_course(db_session, faculty=None)
    book_id, section_id, cluster_id = _make_book_with_cluster(db_session)
    _add_extra_cluster(db_session, book_id, section_id)  # 2 clusters total, only 1 issued below

    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)
    db_session.add(
        IssuedLedgerORM(
            id=uuid.uuid4(),
            course_id=course.id,
            concept_cluster_id=cluster_id,
            variant_id=variant.id,
            problem_set_id=problem_set.id,
            issued_at=datetime.now(UTC),
            is_recycled=False,
        )
    )
    db_session.commit()

    resp = client.get(f"/api/problem-sets/{problem_set.id}")
    assert resp.status_code == 200
    assert resp.json()["remaining_concepts"] == 1  # 2 total - 1 issued


def test_download_handout_and_solutions_pdfs(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    handout = client.get(f"/api/problem-sets/{problem_set.id}/handout.pdf")
    assert handout.status_code == 200
    assert handout.content == b"%PDF-1.4 fake handout"

    solutions = client.get(f"/api/problem-sets/{problem_set.id}/solutions.pdf")
    assert solutions.status_code == 200
    assert solutions.content == b"%PDF-1.4 fake solutions"


def test_download_code_zip_contains_real_files(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    resp = client.get(f"/api/problem-sets/{problem_set.id}/code.zip")
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert zf.namelist() == ["problem_01.py"]
    assert zf.read("problem_01.py").decode() == "print('hi')"


def test_chat_answers_a_question_about_a_step(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PLUMBING ONLY: `explain_step` itself is monkeypatched, so this
    proves the route's index validation and response shape, not that any
    real model gives a good answer -- see test_chat.py for that stage's
    own (also fake-client) prompt/parsing tests."""
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    seen_args: dict[str, object] = {}

    def _fake_explain_step(client_arg: object, job_id: str, variant_arg: object, step_index: int, question: str) -> str:
        seen_args.update(step_index=step_index, question=question)
        return "Because the process is isentropic, so entropy is constant."

    monkeypatch.setattr("api.routers.problem_sets.explain_step", _fake_explain_step)

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/chat",
        json={"problem_index": 1, "step_index": 1, "question": "why?"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"answer": "Because the process is isentropic, so entropy is constant."}
    assert seen_args == {"step_index": 1, "question": "why?"}


def test_chat_returns_404_for_invalid_problem_index(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/chat",
        json={"problem_index": 99, "step_index": 1, "question": "why?"},
    )
    assert resp.status_code == 404


def test_chat_returns_404_for_invalid_step_index(client: TestClient, db_session: Session, tmp_path: Path) -> None:
    course = _make_course(db_session, faculty=None)
    _book_id, _section_id, cluster_id = _make_book_with_cluster(db_session)
    variant = _make_variant(db_session, cluster_id)  # solution_steps == ["Step one."], length 1
    problem_set = _make_rendered_problem_set(db_session, course.id, [variant.id], tmp_path)

    resp = client.post(
        f"/api/problem-sets/{problem_set.id}/chat",
        json={"problem_index": 1, "step_index": 5, "question": "why?"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------


def test_job_status_endpoint_reports_progress_fields(client: TestClient, db_session: Session) -> None:
    job = JobORM(
        id=uuid.uuid4(),
        kind=JobKind.INGEST,
        status=JobStatus.RUNNING,
        stage="extracting",
        pages_done=4,
        pages_total=8,
        extraction_started_at=_now(),
        created_at=_now(),
        updated_at=_now(),
    )
    db_session.add(job)
    db_session.commit()

    resp = client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "extracting"
    assert body["pct"] == 50.0
    assert body["pages_done"] == 4
    assert body["pages_total"] == 8


def test_job_status_404s_on_unknown_id(client: TestClient) -> None:
    resp = client.get(f"/api/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
