"""embedding dim 1024 -> 3072 (Gemini gemini-embedding-001, not BGE-M3)

Revision ID: 0002_gemini_embedding_dim
Revises: 0001_initial_schema
Create Date: 2026-08-09
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_gemini_embedding_dim"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE concept_cards ALTER COLUMN embedding TYPE vector(3072)")
    op.execute("ALTER TABLE concept_clusters ALTER COLUMN centroid_embedding TYPE vector(3072)")


def downgrade() -> None:
    op.execute("ALTER TABLE concept_cards ALTER COLUMN embedding TYPE vector(1024)")
    op.execute("ALTER TABLE concept_clusters ALTER COLUMN centroid_embedding TYPE vector(1024)")
