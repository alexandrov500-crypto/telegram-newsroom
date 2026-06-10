"""Add content_segment to post_growth_validation.

Revision ID: 0008_content_segment
Revises: 0007_validation_status
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_content_segment"
down_revision = "0007_validation_status"
branch_labels = None
depends_on = None


def _column_names(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" not in sa.inspect(bind).get_table_names():
        return
    cols = _column_names(bind, "post_growth_validation")
    if "content_segment" not in cols:
        op.add_column(
            "post_growth_validation",
            sa.Column("content_segment", sa.String(length=32), nullable=False, server_default="general_news"),
        )
        op.create_index(
            "ix_post_growth_validation_content_segment",
            "post_growth_validation",
            ["content_segment"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" not in sa.inspect(bind).get_table_names():
        return
    cols = _column_names(bind, "post_growth_validation")
    if "content_segment" in cols:
        op.drop_index("ix_post_growth_validation_content_segment", table_name="post_growth_validation")
        op.drop_column("post_growth_validation", "content_segment")
