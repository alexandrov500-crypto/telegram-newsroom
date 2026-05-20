"""Add editorial_scores table for Phase 2.1 intelligence layer.

Revision ID: 0002_editorial_scores
Revises: 0001_initial
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_editorial_scores"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "editorial_scores" in _table_names(bind):
        return
    op.create_table(
        "editorial_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("novelty_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_trust_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("duplicate_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cluster_importance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("publish_priority_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("operator_feedback_score", sa.Float(), nullable=True),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("draft_id", name="uq_editorial_scores_draft_id"),
    )
    op.create_index("ix_editorial_scores_draft_id", "editorial_scores", ["draft_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "editorial_scores" not in _table_names(bind):
        return
    op.drop_index("ix_editorial_scores_draft_id", table_name="editorial_scores")
    op.drop_table("editorial_scores")
