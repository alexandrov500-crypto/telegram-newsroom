"""Audience-aware editorial prioritization (aggregate cohort, no per-user tracking)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.growth.engagement_feedback import hour_affinity, load_engagement_feedback, source_affinity, topic_affinity
from app.growth.topic_fatigue import evaluate_topic_fatigue


@dataclass(frozen=True)
class AudiencePriorityScore:
    draft_id: int
    score: float
    components: dict[str, float]
    suppress: bool
    reason: str


def _prefs_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "audience_preference_vectors.json"


def load_audience_preferences(runtime_dir: str) -> dict[str, float]:
    """Cohort-style vertical affinity (macro/crypto/geo) from rolling engagement."""
    feedback = load_engagement_feedback(runtime_dir)
    prefs = dict(feedback.vertical_weights)
    if not prefs:
        prefs = {"macro": 0.35, "finance": 0.35, "geopolitics": 0.35, "crypto": 0.35}
    return prefs


def save_audience_preferences(runtime_dir: str, prefs: dict[str, float]) -> None:
    p = _prefs_path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"updated_at": datetime.now(UTC).isoformat(), "vertical_affinity": prefs}),
        encoding="utf-8",
    )


def score_draft_for_audience(
    *,
    draft_id: int,
    content: str,
    sources_json: str,
    extras_json: str,
    runtime_dir: str,
    newsroom_tz: str = "Europe/Moscow",
    created_at: Any | None = None,
) -> AudiencePriorityScore:
    feedback = load_engagement_feedback(runtime_dir)
    prefs = load_audience_preferences(runtime_dir)

    topic_bucket = "general"
    narrative_id = ""
    signal_score = 0.55
    try:
        ex = json.loads(extras_json or "{}")
        topic_bucket = str(
            ex.get("category")
            or (ex.get("editorial_tags") or {}).get("category")
            or (ex.get("cluster_intelligence") or {}).get("category")
            or "general"
        )
        narrative_id = str((ex.get("narrative_intelligence") or {}).get("narrative_id") or "")
        pub_intel = ex.get("publication_intel") or {}
        if isinstance(pub_intel, dict):
            pri = pub_intel.get("publication_priority") or {}
            if isinstance(pri, dict):
                signal_score = float(pri.get("score") or signal_score) / 100.0 if float(pri.get("score") or 0) > 1 else float(pri.get("score") or signal_score)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    from editorial.cadence import topic_dedupe_key

    topic_key = topic_dedupe_key(topic_bucket)
    fatigue = evaluate_topic_fatigue(
        runtime_dir=runtime_dir,
        topic_key=topic_key,
        content=content,
        narrative_id=narrative_id,
    )
    if fatigue.suppress:
        return AudiencePriorityScore(draft_id, 0.0, {}, True, fatigue.reason)

    vertical = topic_bucket.split("_")[0].lower()
    cohort_affinity = float(prefs.get(vertical, feedback.global_engagement))
    topic_aff = topic_affinity(feedback, topic_bucket)

    primary_source = ""
    try:
        src = json.loads(sources_json or "[]")
        if isinstance(src, list) and src:
            primary_source = str((src[0] or {}).get("channel") or "")
    except (json.JSONDecodeError, TypeError):
        pass
    src_aff = source_affinity(feedback, primary_source)

    try:
        hour = datetime.now(ZoneInfo(newsroom_tz)).hour
    except Exception:
        hour = 12
    slot_aff = hour_affinity(feedback, hour)

    novelty = fatigue.novelty
    momentum_boost = max(0.0, feedback.momentum) * 0.15

    try:
        from app.flywheel.explore_exploit import decide_explore_exploit

        explore = decide_explore_exploit(
            runtime_dir=runtime_dir,
            topic_bucket=topic_bucket,
            novelty=novelty,
            cohort_affinity=cohort_affinity,
            newsroom_tz=newsroom_tz,
        )
        explore_boost = explore.boost
    except Exception:
        explore_boost = 1.0

    habit_boost = 1.0
    try:
        from app.flywheel.retention_habit import active_habit_slot

        slot = active_habit_slot(newsroom_tz)
        if slot:
            habit_boost = slot.cadence_boost
    except Exception:
        pass

    freshness_component = 0.0
    try:
        from app.growth.wire_freshness import (
            draft_age_minutes,
            freshness_boost,
            is_fastlane_source,
            primary_source_from_json,
            wire_freshness_enabled,
        )

        if wire_freshness_enabled() and created_at is not None:
            age = draft_age_minutes(type("_AgeDraft", (), {"created_at": created_at})())
            freshness_component = freshness_boost(age)
            if is_fastlane_source(primary_source_from_json(sources_json)):
                freshness_component = min(1.0, freshness_component * 1.18)
    except Exception:
        freshness_component = 0.0

    score = (
        0.28 * signal_score
        + 0.22 * topic_aff
        + 0.18 * cohort_affinity
        + 0.14 * src_aff
        + 0.10 * slot_aff
        + 0.08 * novelty
        + momentum_boost
        + (0.22 * freshness_component if freshness_component else 0.0)
    ) * explore_boost * habit_boost

    try:
        from app.growth.autonomous_robot.peak_hours import evaluate_peak_hour
        from app.growth.autonomous_robot.topic_boost import topic_boost_multiplier

        score *= topic_boost_multiplier(topic_bucket, runtime_dir)
        peak = evaluate_peak_hour(hour_local=hour, newsroom_tz=newsroom_tz)
        score *= peak.score_multiplier
        components["topic_boost"] = round(topic_boost_multiplier(topic_bucket, runtime_dir), 4)
        components["peak_multiplier"] = round(peak.score_multiplier, 4)
    except Exception:
        pass

    try:
        from app.monetization.audience_value import score_audience_value

        av = score_audience_value(topic_bucket=topic_bucket, runtime_dir=runtime_dir)
        score *= round(0.92 + av.ltv_score * 0.12, 4)
    except Exception:
        pass

    if feedback.low_engagement_streak >= 4 and topic_aff < feedback.global_engagement:
        score *= 0.85

    components = {
        "signal": round(signal_score, 4),
        "topic": round(topic_aff, 4),
        "cohort": round(cohort_affinity, 4),
        "source": round(src_aff, 4),
        "slot": round(slot_aff, 4),
        "novelty": round(novelty, 4),
        "momentum": round(momentum_boost, 4),
        "explore_boost": round(explore_boost, 4),
        "habit_boost": round(habit_boost, 4),
        "freshness": round(freshness_component, 4),
    }
    return AudiencePriorityScore(
        draft_id=draft_id,
        score=round(min(1.0, score), 4),
        components=components,
        suppress=False,
        reason="ok",
    )


def rank_pending_drafts_for_publish(
    drafts: list[Any],
    *,
    settings: Any,
) -> list[Any]:
    runtime_dir = str(getattr(settings, "runtime_state_dir", "") or "")
    tz = str(getattr(settings, "newsroom_timezone", "Europe/Moscow") or "Europe/Moscow")
    scored: list[tuple[float, Any]] = []
    for d in drafts:
        ps = score_draft_for_audience(
            draft_id=int(getattr(d, "id", 0)),
            content=str(getattr(d, "content", "") or ""),
            sources_json=str(getattr(d, "sources", "") or "[]"),
            extras_json=str(getattr(d, "draft_extras", "") or "{}"),
            runtime_dir=runtime_dir,
            newsroom_tz=tz,
            created_at=getattr(d, "created_at", None),
        )
        if ps.suppress:
            continue
        scored.append((ps.score, d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]
