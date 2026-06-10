"""Historical backfill for post_growth_validation from existing tables."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.format.profiles import effective_format_profile, growth_meta_from_draft_extras
from app.growth_layer.segments.content_segments import classify_from_draft_extras
from app.growth_layer.validation.acquisition_proxy import compute_acquisition_components
from app.growth_layer.validation.status import ValidationStatus
from db.models import Draft, DraftGrowthScore, PostGrowthValidation, PostPerformance, PublishedPost
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_SNAPSHOT_PRIORITY = ("t24h", "t6h", "t1h", "t0")


@dataclass
class BackfillStats:
    scanned: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    skipped_no_performance: int = 0
    skipped_existing_final: int = 0
    errors: int = 0
    dry_run: bool = False
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "skipped_no_performance": self.skipped_no_performance,
            "skipped_existing_final": self.skipped_existing_final,
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _primary_source_from_draft(draft: Draft) -> str:
    try:
        src = json.loads(draft.sources or "[]")
        if isinstance(src, list) and src:
            s0 = src[0]
            if isinstance(s0, dict):
                return str(s0.get("channel") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def _topic_bucket_from_draft(draft: Draft) -> str:
    ex = _parse_json(draft.draft_extras)
    return str(ex.get("category") or (ex.get("editorial_tags") or {}).get("category") or "general")


def _prediction_from_sources(
    *,
    growth_score: DraftGrowthScore | None,
    draft: Draft,
) -> tuple[int, str, str]:
    growth = growth_meta_from_draft_extras(draft.draft_extras)
    predicted = 0
    tier = ""
    format_profile = "cb_brief"
    if growth:
        try:
            predicted = int(growth.get("virality_score") or 0)
        except (TypeError, ValueError):
            predicted = 0
        tier = str(growth.get("virality_tier") or "")
        format_profile = effective_format_profile(growth)
    if growth_score is not None:
        if predicted <= 0:
            predicted = int(growth_score.virality_score)
        if not tier:
            tier = str(growth_score.virality_tier or "")
        if format_profile == "cb_brief":
            format_profile = str(growth_score.format_profile or format_profile)
    return predicted, tier, format_profile


def _pick_best_snapshot(snapshots: list[PostPerformance]) -> PostPerformance | None:
    by_label = {str(s.snapshot_label): s for s in snapshots}
    for label in _SNAPSHOT_PRIORITY:
        if label in by_label:
            return by_label[label]
    return snapshots[0] if snapshots else None


def _validation_status_for_snapshot(label: str) -> str:
    if label == "t24h":
        return ValidationStatus.FINAL.value
    if label == "t6h":
        return ValidationStatus.T6_READY.value
    if label in {"t1h", "t0"}:
        return ValidationStatus.PENDING.value
    return ValidationStatus.PENDING.value


def _build_actuals_from_snapshot(snap: PostPerformance) -> dict[str, Any]:
    subs = max(int(snap.subscribers_at_snapshot or 0), 1)
    views = int(snap.views or 0)
    forwards = int(snap.forwards or 0)
    err = round(views / subs, 4)
    forward_rate = round(forwards / max(views, 1), 4)
    engagement = round(float(snap.engagement_score or 0), 4)
    components = compute_acquisition_components(forwards=forwards, err=err, engagement=engagement)
    label = str(snap.snapshot_label or "t0")
    return {
        "actual_engagement": engagement,
        "actual_forwards": forwards,
        "actual_views": views,
        "actual_reactions": int(snap.reactions_total or 0),
        "actual_err": err,
        "actual_forward_rate": forward_rate,
        "actual_virality_score": round(float(snap.virality_score or 0), 4),
        "snapshot_label": label,
        **components,
    }


async def backfill_growth_validation(
    session: AsyncSession,
    *,
    dry_run: bool = False,
    force: bool = False,
    limit: int | None = None,
) -> BackfillStats:
    stats = BackfillStats(dry_run=dry_run)

    q = (
        select(PublishedPost, Draft)
        .join(Draft, Draft.id == PublishedPost.draft_id)
        .order_by(PublishedPost.published_at.desc())
    )
    if limit is not None:
        q = q.limit(max(1, int(limit)))
    pairs = list((await session.execute(q)).all())

    for pub, draft in pairs:
        stats.scanned += 1
        draft_id = int(pub.draft_id)
        try:
            existing = await session.scalar(
                select(PostGrowthValidation).where(PostGrowthValidation.draft_id == draft_id)
            )
            if existing is not None and existing.validation_status == ValidationStatus.FINAL.value and not force:
                stats.skipped += 1
                stats.skipped_existing_final += 1
                continue

            perf_rows = list(
                (
                    await session.execute(
                        select(PostPerformance).where(PostPerformance.draft_id == draft_id)
                    )
                )
                .scalars()
                .all()
            )
            if not perf_rows:
                stats.skipped += 1
                stats.skipped_no_performance += 1
                continue

            snap = _pick_best_snapshot(perf_rows)
            if snap is None:
                stats.skipped += 1
                stats.skipped_no_performance += 1
                continue

            growth_score = await session.scalar(
                select(DraftGrowthScore).where(DraftGrowthScore.draft_id == draft_id)
            )
            predicted, tier, format_profile = _prediction_from_sources(growth_score=growth_score, draft=draft)
            topic_bucket = _topic_bucket_from_draft(draft)
            primary_source = str(snap.primary_source or "") or _primary_source_from_draft(draft)
            content_segment = classify_from_draft_extras(draft.draft_extras, topic_bucket=topic_bucket)
            experiment = {
                "format_profile": format_profile,
                "predicted_virality": predicted,
                "virality_tier": tier,
                "topic_bucket": topic_bucket,
                "primary_source": primary_source,
            }
            actuals = _build_actuals_from_snapshot(snap)
            status = _validation_status_for_snapshot(str(snap.snapshot_label))
            validated_at = snap.snapshot_at or datetime.now(timezone.utc)

            if dry_run:
                stats.details.append(f"draft_id={draft_id} status={status} snapshot={snap.snapshot_label}")
                if existing is None:
                    stats.created += 1
                else:
                    stats.updated += 1
                continue

            if existing is None:
                row = PostGrowthValidation(
                    draft_id=draft_id,
                    telegram_post_id=int(pub.telegram_post_id),
                    channel_id=int(snap.channel_id or 0),
                    published_at=pub.published_at,
                    format_profile=format_profile[:32],
                    predicted_virality=predicted,
                    virality_tier=tier[:32],
                    topic_bucket=topic_bucket[:64],
                    primary_source=primary_source[:255],
                    experiment_json=json.dumps(experiment, ensure_ascii=False),
                    actuals_json=json.dumps(actuals, ensure_ascii=False),
                    content_segment=content_segment[:32],
                    validation_status=status,
                    validated_at=validated_at if status == ValidationStatus.FINAL.value else None,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(row)
                stats.created += 1
            else:
                existing.telegram_post_id = int(pub.telegram_post_id)
                existing.channel_id = int(snap.channel_id or existing.channel_id or 0)
                existing.published_at = pub.published_at
                existing.format_profile = format_profile[:32]
                existing.predicted_virality = predicted
                existing.virality_tier = tier[:32]
                existing.topic_bucket = topic_bucket[:64]
                existing.primary_source = primary_source[:255]
                existing.content_segment = content_segment[:32]
                existing.experiment_json = json.dumps(experiment, ensure_ascii=False)
                existing.actuals_json = json.dumps(actuals, ensure_ascii=False)
                existing.validation_status = status
                if status == ValidationStatus.FINAL.value:
                    existing.validated_at = validated_at
                stats.updated += 1
        except Exception as exc:
            stats.errors += 1
            log_event(logger, "growth.validation.backfill_error", draft_id=draft_id, error=repr(exc)[:120])

    if not dry_run:
        await session.flush()

    log_event(logger, "growth.validation.backfill_complete", **stats.to_dict())
    return stats
