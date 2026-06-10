"""Add validation_status to post_growth_validation.

Revision ID: 0007_validation_status
Revises: 0006_post_growth_validation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_validation_status"
down_revision = "0006_post_growth_validation"
branch_labels = None
depends_on = None


def _column_names(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" not in sa.inspect(bind).get_table_names():
        return
    cols = _column_names(bind, "post_growth_validation")
    if "validation_status" not in cols:
        op.add_column(
            "post_growth_validation",
            sa.Column("validation_status", sa.String(length=16), nullable=False, server_default="PENDING"),
        )
        op.create_index(
            "ix_post_growth_validation_validation_status",
            "post_growth_validation",
            ["validation_status"],
        )
    op.execute(
        """
        UPDATE post_growth_validation
        SET validation_status = 'FINAL'
        WHERE validated_at IS NOT NULL
          AND validation_status = 'PENDING'
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "post_growth_validation" not in sa.inspect(bind).get_table_names():
        return
    cols = _column_names(bind, "post_growth_validation")
    if "validation_status" in cols:
        op.drop_index("ix_post_growth_validation_validation_status", table_name="post_growth_validation")
        op.drop_column("post_growth_validation", "validation_status")
