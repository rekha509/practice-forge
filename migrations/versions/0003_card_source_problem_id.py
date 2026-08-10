"""concept_cards.source_problem_id (NOT NULL, UNIQUE FK to source_problems)

S5 idempotency needs a natural key: a card's identity IS the SourceProblem
it was distilled from. That only works as a real guard if the database
enforces it — a nullable FK can't serve as an idempotency key at all
(`WHERE source_problem_id = X` never matches a NULL row, so any card
still missing the value would just get re-created every re-run), and
without a UNIQUE constraint two concurrent/retried runs could still both
insert a card for the same problem before either commits. So: NOT NULL,
UNIQUE, enforced by the database — not just an application-level check
that a duplicate insert could race past.

The 5 pre-existing concept_cards rows (real dev data from this session's
30-page run, predating this column entirely) have no way to backfill this
value — nothing recorded which SourceProblem produced which card. Per
explicit instruction, they and their dependents (candidate_scores,
concept_clusters) are deleted here rather than leaving the column nullable
to accommodate them.

Revision ID: 0003_card_source_problem_id
Revises: 0002_gemini_embedding_dim
Create Date: 2026-08-10

(Revision id kept short deliberately: alembic_version.version_num is
varchar(32) by default, and the first attempt at this migration used the
full "0003_concept_card_source_problem_id" — 36 chars — which passed the
DDL itself but failed writing the version-bump row, rolling the whole
transaction back cleanly. No partial state resulted; just renamed.)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003_card_source_problem_id"
down_revision: Union[str, None] = "0002_gemini_embedding_dim"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable at first so the following cleanup can identify pre-existing
    # rows (every one of them, since the column doesn't exist for them yet)
    # by "IS NULL" before the NOT NULL constraint is added below.
    op.add_column(
        "concept_cards",
        sa.Column(
            "source_problem_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("source_problems.id"),
            nullable=True,
        ),
    )

    op.execute(
        """
        DELETE FROM candidate_scores
        WHERE concept_card_id IN (
            SELECT id FROM concept_cards WHERE source_problem_id IS NULL
        )
        """
    )
    op.execute(
        """
        DELETE FROM concept_clusters
        WHERE representative_card_id IN (
            SELECT id FROM concept_cards WHERE source_problem_id IS NULL
        )
        OR member_card_ids && ARRAY(
            SELECT id FROM concept_cards WHERE source_problem_id IS NULL
        )
        """
    )
    op.execute("DELETE FROM concept_cards WHERE source_problem_id IS NULL")

    op.alter_column("concept_cards", "source_problem_id", nullable=False)
    op.create_unique_constraint(
        "uq_concept_cards_source_problem_id", "concept_cards", ["source_problem_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_concept_cards_source_problem_id", "concept_cards", type_="unique"
    )
    op.alter_column("concept_cards", "source_problem_id", nullable=True)
    op.drop_column("concept_cards", "source_problem_id")
