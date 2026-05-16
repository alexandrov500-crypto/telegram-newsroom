"""Initial newsroom schema (SQLite-safe, idempotent create).

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-14

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _table_names(bind) -> set[str]:
    insp = sa.inspect(bind)
    return set(insp.get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    names = _table_names(bind)

    if "raw_posts" not in names:
        op.create_table(
            "raw_posts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_name", sa.String(length=255), nullable=False, index=True),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("channel_name", "message_id", name="uq_raw_channel_message"),
        )

    names = _table_names(bind)
    if "drafts" not in names:
        op.create_table(
            "drafts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("sources", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("admin_chat_message_id", sa.Integer(), nullable=True),
            sa.Column("editor_title", sa.Text(), nullable=True),
            sa.Column("editor_summary", sa.Text(), nullable=True),
            sa.Column("draft_extras", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("edit_history", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("scheduled_publish_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_publish_error", sa.Text(), nullable=True),
            sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_drafts_content_hash", "drafts", ["content_hash"])
        op.create_index("ix_drafts_status", "drafts", ["status"])
        op.create_index("ix_drafts_scheduled_publish_at", "drafts", ["scheduled_publish_at"])

    names = _table_names(bind)
    if "published_posts" not in names:
        op.create_table(
            "published_posts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("draft_id", sa.Integer(), sa.ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("telegram_post_id", sa.Integer(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("draft_id", name="uq_published_posts_draft_id"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    names = _table_names(bind)
    if "published_posts" in names:
        op.drop_table("published_posts")
    names = _table_names(bind)
    if "drafts" in names:
        op.drop_table("drafts")
    names = _table_names(bind)
    if "raw_posts" in names:
        op.drop_table("raw_posts")
