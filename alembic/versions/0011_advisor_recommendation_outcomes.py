"""Add advisor_recommendation_outcomes for Phase 3B advisor validation.

Revision ID: 0011_advisor_recommendation_outcomes
Revises: 0010_draft_growth_advice
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_advisor_recommendation_outcomes"
down_revision = "0010_draft_growth_advice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "advisor_recommendation_outcomes" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "advisor_recommendation_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommendation_type", sa.String(length=64), nullable=False),
        sa.Column("adopted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alignment_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alignment_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actual_err", sa.Float(), nullable=True),
        sa.Column("actual_forwards", sa.Integer(), nullable=True),
        sa.Column("actual_engagement", sa.Float(), nullable=True),
        sa.Column("actual_virality", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("draft_id", "recommendation_type", name="uq_advisor_outcome_draft_rec"),
    )
    op.create_index("ix_advisor_outcomes_draft_id", "advisor_recommendation_outcomes", ["draft_id"])
    op.create_index("ix_advisor_outcomes_post_id", "advisor_recommendation_outcomes", ["post_id"])
    op.create_index("ix_advisor_outcomes_rec_type", "advisor_recommendation_outcomes", ["recommendation_type"])


def downgrade() -> None:
    bind = op.get_bind()
    if "advisor_recommendation_outcomes" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_advisor_outcomes_rec_type", table_name="advisor_recommendation_outcomes")
    op.drop_index("ix_advisor_outcomes_post_id", table_name="advisor_recommendation_outcomes")
    op.drop_index("ix_advisor_outcomes_draft_id", table_name="advisor_recommendation_outcomes")
    op.drop_table("advisor_recommendation_outcomes")
