"""Add draft_growth_scores for Growth Layer virality predictions.

Revision ID: 0005_draft_growth_scores
Revises: 0004_deactivate_broken_sources
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_draft_growth_scores"
down_revision = "0004_deactivate_broken_sources"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "draft_growth_scores" in _table_names(bind):
        return
    op.create_table(
        "draft_growth_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("virality_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("virality_tier", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("novelty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("economic_impact", sa.Float(), nullable=False, server_default="0"),
        sa.Column("audience_relevance", sa.Float(), nullable=False, server_default="0"),
        sa.Column("emotional_trigger", sa.Float(), nullable=False, server_default="0"),
        sa.Column("shareability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("format_profile", sa.String(length=32), nullable=False, server_default="cb_brief"),
        sa.Column("reasons_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("model_version", sa.String(length=32), nullable=False, server_default="v1-heuristic-signal-bridge"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_draft_growth_scores_draft_id", "draft_growth_scores", ["draft_id"], unique=True)
    op.create_index("ix_draft_growth_scores_virality_score", "draft_growth_scores", ["virality_score"])
    op.create_index("ix_draft_growth_scores_virality_tier", "draft_growth_scores", ["virality_tier"])


def downgrade() -> None:
    bind = op.get_bind()
    if "draft_growth_scores" not in _table_names(bind):
        return
    op.drop_index("ix_draft_growth_scores_virality_tier", table_name="draft_growth_scores")
    op.drop_index("ix_draft_growth_scores_virality_score", table_name="draft_growth_scores")
    op.drop_index("ix_draft_growth_scores_draft_id", table_name="draft_growth_scores")
    op.drop_table("draft_growth_scores")
