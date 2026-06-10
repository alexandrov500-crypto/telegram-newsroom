"""Add draft_growth_advice for Phase 3A pre-publication advisor.

Revision ID: 0010_draft_growth_advice
Revises: 0009_post_editorial_features
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_draft_growth_advice"
down_revision = "0009_post_editorial_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "draft_growth_advice" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "draft_growth_advice",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alignment_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("headline_alignment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("structure_alignment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("segment_alignment", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predicted_segment", sa.String(length=32), nullable=False, server_default="general_news"),
        sa.Column("recommendations_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_draft_growth_advice_draft_id", "draft_growth_advice", ["draft_id"], unique=True)
    op.create_index("ix_draft_growth_advice_alignment_score", "draft_growth_advice", ["alignment_score"])
    op.create_index("ix_draft_growth_advice_predicted_segment", "draft_growth_advice", ["predicted_segment"])


def downgrade() -> None:
    bind = op.get_bind()
    if "draft_growth_advice" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_draft_growth_advice_predicted_segment", table_name="draft_growth_advice")
    op.drop_index("ix_draft_growth_advice_alignment_score", table_name="draft_growth_advice")
    op.drop_index("ix_draft_growth_advice_draft_id", table_name="draft_growth_advice")
    op.drop_table("draft_growth_advice")
