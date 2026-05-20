"""Editorial scoring contract columns (version, operator feedback label).

Revision ID: 0003_editorial_scoring_contract
Revises: 0002_editorial_scores
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_editorial_scoring_contract"
down_revision = "0002_editorial_scores"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    if "editorial_scores" not in sa.inspect(bind).get_table_names():
        return
    cols = _columns(bind, "editorial_scores")
    if "scoring_version" not in cols:
        op.add_column(
            "editorial_scores",
            sa.Column("scoring_version", sa.String(length=32), nullable=False, server_default="phase2.1-v1"),
        )
    if "operator_feedback_label" not in cols:
        op.add_column(
            "editorial_scores",
            sa.Column("operator_feedback_label", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "editorial_scores" not in sa.inspect(bind).get_table_names():
        return
    cols = _columns(bind, "editorial_scores")
    if "operator_feedback_label" in cols:
        op.drop_column("editorial_scores", "operator_feedback_label")
    if "scoring_version" in cols:
        op.drop_column("editorial_scores", "scoring_version")
