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
    extras: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
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
    operator_feedback_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False, default="phase2.1-v1")
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishedPost(Base):
    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(ForeignKey("drafts.id", ondelete="CASCADE"), unique=True, nullable=False)
    telegram_post_id: Mapped[int] = mapped_column(Integer, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    draft: Mapped["Draft"] = relationship(back_populates="published")


class PipelineTick(Base):
    """Persisted scheduler pipeline tick (stuck detection, ops audit)."""

    __tablename__ = "pipeline_ticks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drafts_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    correlation_id: Mapped[str] = mapped_column(String(96), nullable=False, default="", index=True)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class OperatorFeedback(Base):
    """Structured operator actions (advisory; never bypasses publish gates)."""

    __tablename__ = "operator_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tick_id: Mapped[str] = mapped_column(String(96), nullable=False, default="", index=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    applied: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)
    apply_reason: Mapped[str] = mapped_column(String(240), nullable=False, default="")


class FailedDraftQueue(Base):
    """Retry queue for transient publish failures (not editorial rejects)."""

    __tablename__ = "failed_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(96), nullable=False, default="")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    terminal_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    error_category: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)


class PostPerformance(Base):
    """Measured Telegram post metrics (views/forwards/reactions) at scheduled snapshots."""

    __tablename__ = "post_performance"
    __table_args__ = (
        UniqueConstraint("draft_id", "snapshot_label", name="uq_post_perf_draft_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int | None] = mapped_column(
        ForeignKey("drafts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    telegram_post_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    snapshot_label: Mapped[str] = mapped_column(String(16), nullable=False, default="t0")
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    forwards: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reactions_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscribers_at_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engagement_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    virality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    primary_source: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    topic_bucket: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    publish_hour_local: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class ChannelAudienceSnapshot(Base):
    """Subscriber count time series for growth delta tracking."""

    __tablename__ = "channel_audience_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delta_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delta_7d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SourceRegistryEntry(Base):
    """Curated source metadata for tiered polling and probation."""

    __tablename__ = "source_registry"
    __table_args__ = (UniqueConstraint("handle", name="uq_source_registry_handle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    handle: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(8), nullable=False, default="T2", index=True)
    vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    trust_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.72)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    probation_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NarrativeTrack(Base):
    """Long-lived narrative arcs for continuation detection and digest carryover."""

    __tablename__ = "narrative_tracks"
    __table_args__ = (UniqueConstraint("narrative_id", name="uq_narrative_tracks_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    narrative_id: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    cluster_key: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    vertical: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    momentum_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    publish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_narrative_id: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    context_tokens_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PerformanceArchetypeMemory(Base):
    """Learned post archetype / headline / slot performance."""

    __tablename__ = "performance_archetype_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    archetype: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    headline_pattern: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    topic_bucket: Mapped[str] = mapped_column(String(32), nullable=False, default="general", index=True)
    publish_hour_local: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_engagement: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_virality: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GrowthDigestRun(Base):
    """Retention digests — morning briefing, evening recap, weekly key events."""

    __tablename__ = "growth_digest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    digest_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diversity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class EditorialStyleMemory(Base):
    """Successful content patterns for identity consistency."""

    __tablename__ = "editorial_style_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vertical: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    headline_pattern: Mapped[str] = mapped_column(String(48), nullable=False, default="")
    style_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    insight_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_engagement: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class EditorialIdentityVector(Base):
    """Compressed long-term editorial fingerprint."""

    __tablename__ = "editorial_identity_vectors"
    __table_args__ = (UniqueConstraint("key", name="uq_editorial_identity_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    vector_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CohortMemory(Base):
    """Aggregate audience cohort affinity (macro/crypto/geo)."""

    __tablename__ = "cohort_memory"
    __table_args__ = (UniqueConstraint("cohort", name="uq_cohort_memory_cohort"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cohort: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    affinity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.33)
    engagement_sum: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class DistributionFlywheelLog(Base):
    """Cross-post and routing audit trail."""

    __tablename__ = "distribution_flywheel_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    surface: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(24), nullable=False, default="", index=True)
    mirrored_digest: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
