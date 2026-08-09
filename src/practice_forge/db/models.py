"""SQLAlchemy ORM tables mirroring practice_forge.models exactly.

These are the persisted, validated Pydantic models' storage layer — no stage
in the pipeline passes raw LLM prose between stages, it passes rows shaped
like these.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    TIMESTAMP,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from practice_forge.db.base import Base
from practice_forge.models.enums import (
    DifficultyLevel,
    ExtensionType,
    FigureDependency,
    FigureKind,
    IngestStatus,
    ProblemKind,
    VerificationStatus,
)

# BGE-M3 dense embedding dimension.
EMBEDDING_DIM = 1024


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class DisciplineORM(Base):
    __tablename__ = "disciplines"

    id: Mapped[uuid.UUID] = _uuid_pk()
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    solver_libs: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    ml_libs: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    allowed_extension_types: Mapped[list[str]] = mapped_column(
        ARRAY(SAEnum(ExtensionType, native_enum=False)), nullable=False
    )
    sandbox_image_tag: Mapped[str] = mapped_column(String, nullable=False)


class TopicNodeORM(Base):
    __tablename__ = "topic_nodes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disciplines.id"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("topic_nodes.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    syllabus_code: Mapped[str | None] = mapped_column(String, nullable=True)


class CourseORM(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disciplines.id"), nullable=False
    )
    faculty_name: Mapped[str] = mapped_column(String, nullable=False)
    institution: Mapped[str] = mapped_column(String, nullable=False)


class BookORM(Base):
    __tablename__ = "books"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    edition: Mapped[str | None] = mapped_column(String, nullable=True)
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disciplines.id"), nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ingest_status: Mapped[IngestStatus] = mapped_column(
        SAEnum(IngestStatus, native_enum=False), nullable=False, default=IngestStatus.PENDING
    )
    file_sha256: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    minhash_signature: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )
    canonical_book_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=True
    )
    uploaded_by: Mapped[str] = mapped_column(String, nullable=False)


class PageORM(Base):
    __tablename__ = "pages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    book_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown: Mapped[str] = mapped_column(String, nullable=False)
    has_math: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_figure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unit_system_detected: Mapped[str | None] = mapped_column(String, nullable=True)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (Index("uq_pages_book_page_no", "book_id", "page_no", unique=True),)


class SectionORM(Base):
    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    book_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    chapter_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_node_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )


class FigureORM(Base):
    __tablename__ = "figures"

    id: Mapped[uuid.UUID] = _uuid_pk()
    book_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    image_path: Mapped[str] = mapped_column(String, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    figure_kind: Mapped[FigureKind] = mapped_column(
        SAEnum(FigureKind, native_enum=False), nullable=False
    )
    structured_spec_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interpretation_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class SourceProblemORM(Base):
    __tablename__ = "source_problems"

    id: Mapped[uuid.UUID] = _uuid_pk()
    book_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sections.id"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[ProblemKind] = mapped_column(SAEnum(ProblemKind, native_enum=False), nullable=False)
    statement_md: Mapped[str] = mapped_column(String, nullable=False)
    given: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    find: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    solution_md: Mapped[str | None] = mapped_column(String, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    figure_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )
    figure_dependency: Mapped[FigureDependency] = mapped_column(
        SAEnum(FigureDependency, native_enum=False),
        nullable=False,
        default=FigureDependency.NONE,
    )
    is_solvable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ConceptCardORM(Base):
    __tablename__ = "concept_cards"

    id: Mapped[uuid.UUID] = _uuid_pk()
    book_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.id"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sections.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    topic_node_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )
    governing_equations_latex: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    canonical_equation_srepr: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    solution_strategy: Mapped[str] = mapped_column(String, nullable=False)
    typical_pitfalls: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    given_dimensions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    solve_for_dimension: Mapped[str] = mapped_column(String, nullable=False)
    method_tag: Mapped[str] = mapped_column(String, nullable=False)

    continuous_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    has_degradation_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_design_tradeoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_tolerance_spec: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # sha256 over sorted canonical_equation_srepr + sorted given_dimensions +
    # solve_for_dimension + method_tag (see concept.py / fingerprint.py).
    concept_fingerprint: Mapped[str] = mapped_column(String, nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    source_pages: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False, default=list)


class ConceptClusterORM(Base):
    __tablename__ = "concept_clusters"

    id: Mapped[uuid.UUID] = _uuid_pk()
    discipline_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("disciplines.id"), nullable=False
    )
    representative_card_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("concept_cards.id"), nullable=False
    )
    member_card_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    centroid_embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)


class CandidateScoreORM(Base):
    __tablename__ = "candidate_scores"

    id: Mapped[uuid.UUID] = _uuid_pk()
    concept_card_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("concept_cards.id"), nullable=False, unique=True
    )

    pedagogical_value: Mapped[float] = mapped_column(Float, nullable=False)
    computational_suitability: Mapped[float] = mapped_column(Float, nullable=False)
    self_containedness: Mapped[float] = mapped_column(Float, nullable=False)
    syllabus_centrality: Mapped[float] = mapped_column(Float, nullable=False)
    verifiability: Mapped[float] = mapped_column(Float, nullable=False)
    ml_extension_potential: Mapped[float] = mapped_column(Float, nullable=False)

    eligible_extension_types: Mapped[list[str]] = mapped_column(
        ARRAY(SAEnum(ExtensionType, native_enum=False)), nullable=False, default=list
    )
    composite_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        SAEnum(DifficultyLevel, native_enum=False), nullable=False
    )
    scoring_rationale: Mapped[dict] = mapped_column(JSONB, nullable=False)


class VariantORM(Base):
    __tablename__ = "variants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    concept_cluster_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("concept_clusters.id"), nullable=False
    )
    statement_md: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    difficulty: Mapped[DifficultyLevel] = mapped_column(
        SAEnum(DifficultyLevel, native_enum=False), nullable=False
    )
    topic_node_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False, default=list
    )
    solution_steps: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)

    core_python_code: Mapped[str] = mapped_column(String, nullable=False)
    extension_type: Mapped[ExtensionType] = mapped_column(
        SAEnum(ExtensionType, native_enum=False), nullable=False, default=ExtensionType.NONE
    )
    extension_python_code: Mapped[str | None] = mapped_column(String, nullable=True)
    extension_learning_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    extension_figure_paths: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    extension_metrics_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    verified_answer: Mapped[str | None] = mapped_column(String, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False),
        nullable=False,
        default=VerificationStatus.PENDING,
    )
    verification_log: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )

    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_ref: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_recycled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ProblemSetORM(Base):
    __tablename__ = "problem_sets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    variant_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    typst_source: Mapped[str] = mapped_column(String, nullable=False)
    student_pdf_path: Mapped[str] = mapped_column(String, nullable=False)
    solutions_pdf_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        Index("uq_problem_sets_course_run", "course_id", "run_number", unique=True),
    )


class IssuedLedgerORM(Base):
    __tablename__ = "issued_ledger"

    id: Mapped[uuid.UUID] = _uuid_pk()
    course_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    concept_cluster_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("concept_clusters.id"), nullable=False
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("variants.id"), nullable=False
    )
    problem_set_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("problem_sets.id"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    # Denormalized from Variant.is_recycled at write time (S10 writes both in
    # the same transaction). Lets the no-repeat guarantee be enforced as a
    # single partial unique index rather than a cross-table trigger.
    is_recycled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index(
            "uq_issued_ledger_course_cluster_unless_recycled",
            "course_id",
            "concept_cluster_id",
            unique=True,
            postgresql_where=text("is_recycled = false"),
        ),
    )
