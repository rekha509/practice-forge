"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-09
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "disciplines",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String, nullable=False, unique=True),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("solver_libs", pg.ARRAY(sa.String), nullable=False),
        sa.Column("ml_libs", pg.ARRAY(sa.String), nullable=False),
        sa.Column("allowed_extension_types", pg.ARRAY(sa.String), nullable=False),
        sa.Column("sandbox_image_tag", sa.String, nullable=False),
    )

    op.create_table(
        "topic_nodes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), sa.ForeignKey("disciplines.id"), nullable=False),
        sa.Column("parent_id", pg.UUID(as_uuid=True), sa.ForeignKey("topic_nodes.id"), nullable=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("aliases", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("syllabus_code", sa.String, nullable=True),
    )

    op.create_table(
        "courses",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), sa.ForeignKey("disciplines.id"), nullable=False),
        sa.Column("faculty_name", sa.String, nullable=False),
        sa.Column("institution", sa.String, nullable=False),
    )

    op.create_table(
        "books",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("authors", pg.ARRAY(sa.String), nullable=False),
        sa.Column("edition", sa.String, nullable=True),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), sa.ForeignKey("disciplines.id"), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("ingest_status", sa.String, nullable=False, server_default="pending"),
        sa.Column("file_sha256", sa.String, nullable=False, unique=True),
        sa.Column("minhash_signature", pg.ARRAY(sa.Integer), nullable=False, server_default="{}"),
        sa.Column("canonical_book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=True),
        sa.Column("uploaded_by", sa.String, nullable=False),
    )

    op.create_table(
        "pages",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("page_no", sa.Integer, nullable=False),
        sa.Column("markdown", sa.String, nullable=False),
        sa.Column("has_math", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("has_figure", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("unit_system_detected", sa.String, nullable=True),
        sa.Column("extraction_confidence", sa.Float, nullable=False),
    )
    op.create_index("uq_pages_book_page_no", "pages", ["book_id", "page_no"], unique=True)

    op.create_table(
        "sections",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("chapter_no", sa.Integer, nullable=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("page_start", sa.Integer, nullable=False),
        sa.Column("page_end", sa.Integer, nullable=False),
        sa.Column("topic_node_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"),
    )

    op.create_table(
        "figures",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("page_no", sa.Integer, nullable=False),
        sa.Column("label", sa.String, nullable=True),
        sa.Column("image_path", sa.String, nullable=False),
        sa.Column("bbox", pg.ARRAY(sa.Float), nullable=False),
        sa.Column("figure_kind", sa.String, nullable=False),
        sa.Column("structured_spec_json", pg.JSONB, nullable=True),
        sa.Column("interpretation_confidence", sa.Float, nullable=False, server_default="0"),
    )

    op.create_table(
        "source_problems",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("section_id", pg.UUID(as_uuid=True), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("page_no", sa.Integer, nullable=False),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("statement_md", sa.String, nullable=False),
        sa.Column("given", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("find", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("solution_md", sa.String, nullable=True),
        sa.Column("final_answer", sa.String, nullable=True),
        sa.Column("figure_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("figure_dependency", sa.String, nullable=False, server_default="none"),
        sa.Column("is_solvable", sa.Boolean, nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "concept_cards",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=False),
        sa.Column("section_id", pg.UUID(as_uuid=True), sa.ForeignKey("sections.id"), nullable=False),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("topic_node_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("governing_equations_latex", pg.ARRAY(sa.String), nullable=False),
        sa.Column("canonical_equation_srepr", pg.ARRAY(sa.String), nullable=False),
        sa.Column("assumptions", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("solution_strategy", sa.String, nullable=False),
        sa.Column("typical_pitfalls", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("given_dimensions", pg.ARRAY(sa.String), nullable=False),
        sa.Column("solve_for_dimension", sa.String, nullable=False),
        sa.Column("method_tag", sa.String, nullable=False),
        sa.Column("continuous_param_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("has_degradation_mode", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("has_design_tradeoff", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("has_tolerance_spec", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("concept_fingerprint", sa.String, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("source_pages", pg.ARRAY(sa.Integer), nullable=False, server_default="{}"),
    )
    op.create_index("ix_concept_cards_fingerprint", "concept_cards", ["concept_fingerprint"])

    op.create_table(
        "concept_clusters",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("discipline_id", pg.UUID(as_uuid=True), sa.ForeignKey("disciplines.id"), nullable=False),
        sa.Column(
            "representative_card_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("concept_cards.id"),
            nullable=False,
        ),
        sa.Column("member_card_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False),
        sa.Column("centroid_embedding", Vector(EMBEDDING_DIM), nullable=False),
    )

    op.create_table(
        "candidate_scores",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "concept_card_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("concept_cards.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("pedagogical_value", sa.Float, nullable=False),
        sa.Column("computational_suitability", sa.Float, nullable=False),
        sa.Column("self_containedness", sa.Float, nullable=False),
        sa.Column("syllabus_centrality", sa.Float, nullable=False),
        sa.Column("verifiability", sa.Float, nullable=False),
        sa.Column("ml_extension_potential", sa.Float, nullable=False),
        sa.Column("eligible_extension_types", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("composite_score", sa.Float, nullable=False),
        sa.Column("difficulty", sa.String, nullable=False),
        sa.Column("scoring_rationale", pg.JSONB, nullable=False),
    )
    op.create_index("ix_candidate_scores_composite", "candidate_scores", ["composite_score"])

    op.create_table(
        "variants",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "concept_cluster_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("concept_clusters.id"),
            nullable=False,
        ),
        sa.Column("statement_md", sa.String, nullable=False),
        sa.Column("params", pg.JSONB, nullable=False),
        sa.Column("difficulty", sa.String, nullable=False),
        sa.Column("topic_node_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("solution_steps", pg.ARRAY(sa.String), nullable=False),
        sa.Column("core_python_code", sa.String, nullable=False),
        sa.Column("extension_type", sa.String, nullable=False, server_default="none"),
        sa.Column("extension_python_code", sa.String, nullable=True),
        sa.Column("extension_learning_notes", sa.String, nullable=True),
        sa.Column("extension_figure_paths", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("extension_metrics_json", pg.JSONB, nullable=True),
        sa.Column("verified_answer", sa.String, nullable=True),
        sa.Column("verification_status", sa.String, nullable=False, server_default="pending"),
        sa.Column("verification_log", pg.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("needs_review", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source_ref", pg.JSONB, nullable=False),
        sa.Column("is_recycled", sa.Boolean, nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "problem_sets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", pg.UUID(as_uuid=True), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("run_number", sa.Integer, nullable=False),
        sa.Column("variant_ids", pg.ARRAY(pg.UUID(as_uuid=True)), nullable=False),
        sa.Column("typst_source", sa.String, nullable=False),
        sa.Column("student_pdf_path", sa.String, nullable=False),
        sa.Column("solutions_pdf_path", sa.String, nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_problem_sets_course_run", "problem_sets", ["course_id", "run_number"], unique=True
    )

    op.create_table(
        "issued_ledger",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", pg.UUID(as_uuid=True), sa.ForeignKey("courses.id"), nullable=False),
        sa.Column(
            "concept_cluster_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("concept_clusters.id"),
            nullable=False,
        ),
        sa.Column("variant_id", pg.UUID(as_uuid=True), sa.ForeignKey("variants.id"), nullable=False),
        sa.Column(
            "problem_set_id", pg.UUID(as_uuid=True), sa.ForeignKey("problem_sets.id"), nullable=False
        ),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("is_recycled", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_issued_ledger_course_cluster_unless_recycled",
        "issued_ledger",
        ["course_id", "concept_cluster_id"],
        unique=True,
        postgresql_where=sa.text("is_recycled = false"),
    )


def downgrade() -> None:
    op.drop_table("issued_ledger")
    op.drop_table("problem_sets")
    op.drop_table("variants")
    op.drop_table("candidate_scores")
    op.drop_table("concept_clusters")
    op.drop_table("concept_cards")
    op.drop_table("source_problems")
    op.drop_table("figures")
    op.drop_table("sections")
    op.drop_table("pages")
    op.drop_table("books")
    op.drop_table("courses")
    op.drop_table("topic_nodes")
    op.drop_table("disciplines")
