"""faculty table (per-faculty bearer token, docs/adr/0010) + courses.faculty_id
+ jobs table (P10 async ingest/generate progress tracking)

Revision ID: 0004_faculty_and_jobs
Revises: 0003_card_source_problem_id
Create Date: 2026-08-10
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004_faculty_and_jobs"
down_revision: Union[str, None] = "0003_card_source_problem_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "faculty",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("institution", sa.String, nullable=False),
        sa.Column("token", sa.String, nullable=False, unique=True),
    )

    op.add_column(
        "courses",
        sa.Column(
            "faculty_id", pg.UUID(as_uuid=True), sa.ForeignKey("faculty.id"), nullable=True
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("stage", sa.String, nullable=False, server_default=""),
        sa.Column("error_message", sa.String, nullable=True),
        sa.Column("bytes_received", sa.Integer, nullable=True),
        sa.Column("bytes_total", sa.Integer, nullable=True),
        sa.Column("pages_done", sa.Integer, nullable=True),
        sa.Column("pages_total", sa.Integer, nullable=True),
        sa.Column("items_done", sa.Integer, nullable=True),
        sa.Column("items_total", sa.Integer, nullable=True),
        sa.Column("upload_path", sa.String, nullable=True),
        sa.Column("discipline_key", sa.String, nullable=True),
        sa.Column("params", pg.JSONB, nullable=True),
        sa.Column("book_id", pg.UUID(as_uuid=True), sa.ForeignKey("books.id"), nullable=True),
        sa.Column("course_id", pg.UUID(as_uuid=True), sa.ForeignKey("courses.id"), nullable=True),
        sa.Column(
            "result_problem_set_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("problem_sets.id"),
            nullable=True,
        ),
        sa.Column(
            "created_by_faculty_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("faculty.id"),
            nullable=True,
        ),
        sa.Column("extraction_started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_column("courses", "faculty_id")
    op.drop_table("faculty")
