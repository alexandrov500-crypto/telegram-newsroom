"""Add post_growth_validation for Growth Validation Layer.

Revision ID: 0006_post_growth_validation
Revises: 0005_draft_growth_scores
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_post_growth_validation"
down_revision = "0005_draft_growth_scores"
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" in _table_names(bind):
        return
    op.create_table(
        "post_growth_validation",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_post_id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format_profile", sa.String(length=32), nullable=False, server_default="cb_brief"),
        sa.Column("predicted_virality", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("virality_tier", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("topic_bucket", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("primary_source", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("experiment_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actuals_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_post_growth_validation_draft_id", "post_growth_validation", ["draft_id"], unique=True)
    op.create_index("ix_post_growth_validation_telegram_post_id", "post_growth_validation", ["telegram_post_id"])
    op.create_index("ix_post_growth_validation_published_at", "post_growth_validation", ["published_at"])
    op.create_index("ix_post_growth_validation_format_profile", "post_growth_validation", ["format_profile"])


def downgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" not in _table_names(bind):
        return
    op.drop_index("ix_post_growth_validation_format_profile", table_name="post_growth_validation")
    op.drop_index("ix_post_growth_validation_published_at", table_name="post_growth_validation")
    op.drop_index("ix_post_growth_validation_telegram_post_id", table_name="post_growth_validation")
    op.drop_index("ix_post_growth_validation_draft_id", table_name="post_growth_validation")
    op.drop_table("post_growth_validation")
