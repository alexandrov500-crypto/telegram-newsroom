"""Deactivate broken Telethon source handles in source_registry.

Revision ID: 0004_deactivate_broken_sources
Revises: 0003_editorial_scoring_contract
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_deactivate_broken_sources"
down_revision = "0003_editorial_scoring_contract"
branch_labels = None
depends_on = None

_BROKEN = ("reutersbiz", "ft", "energyworldnews", "macro_alerts")


def upgrade() -> None:
    bind = op.get_bind()
    if "source_registry" not in sa.inspect(bind).get_table_names():
        return
    placeholders = ", ".join(f":h{i}" for i in range(len(_BROKEN)))
    params = {f"h{i}": h for i, h in enumerate(_BROKEN)}
    op.execute(
        sa.text(
            f"""
            UPDATE source_registry
            SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
            WHERE lower(handle) IN ({placeholders}) AND status != 'inactive'
            """
        ),
        params,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "source_registry" not in sa.inspect(bind).get_table_names():
        return
    placeholders = ", ".join(f":h{i}" for i in range(len(_BROKEN)))
    params = {f"h{i}": h for i, h in enumerate(_BROKEN)}
    op.execute(
        sa.text(
            f"""
            UPDATE source_registry
            SET status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE lower(handle) IN ({placeholders}) AND status = 'inactive'
            """
        ),
        params,
    )
