from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DraftStatus(str, enum.Enum):
    """Draft lifecycle (stored lowercase in SQLite for backward compatibility)."""

    PENDING = "pending"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    FAILED = "failed"


class RawPost(Base):
    __tablename__ = "raw_posts"
    __table_args__ = (UniqueConstraint("channel_name", "message_id", name="uq_raw_channel_message"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    sources: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DraftStatus.PENDING.value, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    admin_chat_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Editorial overrides & metadata (JSON strings for SQLite simplicity)
    editor_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    editor_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_extras: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    edit_history: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Scheduling & publish diagnostics
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    published: Mapped["PublishedPost | None"] = relationship(back_populates="draft", uselist=False)


class RuntimeOpsState(Base):
    """Singleton row persisted across restarts for ops continuity."""

    __tablename__ = "runtime_ops_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    polling_instance_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    last_degraded_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_recovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_transition_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class EditorialScore(Base):
    """Explainable editorial intelligence per draft (Phase 2.1)."""

    __tablename__ = "editorial_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    novelty_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duplicate_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cluster_importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    publish_priority_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    operator_feedback_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishedPost(Base):
    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), unique=True, nullable=False)
    telegram_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    draft: Mapped["Draft"] = relationship(back_populates="published")
