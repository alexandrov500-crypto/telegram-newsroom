"""Add post_editorial_features for Phase 2C editorial intelligence.

Revision ID: 0009_post_editorial_features
Revises: 0008_content_segment
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_post_editorial_features"
down_revision = "0008_content_segment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "post_editorial_features" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "post_editorial_features",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("headline_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("headline_word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_currency", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_question", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_colon", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_quote", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("uppercase_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("body_length", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paragraph_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bullet_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emoji_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("link_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_segment", sa.String(length=32), nullable=False, server_default="general_news"),
        sa.Column("format_profile", sa.String(length=32), nullable=False, server_default="cb_brief"),
        sa.Column("virality_tier", sa.String(length=32), nullable=False, server_default="standard"),
        sa.Column("features_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_post_editorial_features_draft_id", "post_editorial_features", ["draft_id"], unique=True)
    op.create_index("ix_post_editorial_features_content_segment", "post_editorial_features", ["content_segment"])


def downgrade() -> None:
    bind = op.get_bind()
    if "post_editorial_features" not in sa.inspect(bind).get_table_names():
        return
    op.drop_index("ix_post_editorial_features_content_segment", table_name="post_editorial_features")
    op.drop_index("ix_post_editorial_features_draft_id", table_name="post_editorial_features")
    op.drop_table("post_editorial_features")
