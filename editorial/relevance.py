"""Unified explainable relevance (0–100) for raw clusters / drafts."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from db.models import RawPost

from editorial.event_models import EventEvolution


@dataclass(slots=True)
class RelevanceBreakdown:
    """Component scores in ``[0, 1]`` plus weighted ``total`` in ``[0, 100]``."""

    freshness: float
    source_reputation: float
    topic_momentum: float
    entity_importance: float
    novelty: float
    duplicate_suppression: float
    editorial_preference_boost: float
    weights: dict[str, float] = field(default_factory=dict)
    total: float = 0.0
    notes: tuple[str, ...] = ()
    policy_delta: float = 0.0
    policy_notes: tuple[str, ...] = ()
    policy_adjustments: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "freshness": round(self.freshness, 4),
            "source_reputation": round(self.source_reputation, 4),
            "topic_momentum": round(self.topic_momentum, 4),
            "entity_importance": round(self.entity_importance, 4),
            "novelty": round(self.novelty, 4),
            "duplicate_suppression": round(self.duplicate_suppression, 4),
            "editorial_preference_boost": round(self.editorial_preference_boost, 4),
            "weights": dict(self.weights),
            "total": round(self.total, 2),
            "notes": list(self.notes),
            "policy_delta": round(self.policy_delta, 4),
            "policy_notes": list(self.policy_notes),
            "policy_adjustments": dict(self.policy_adjustments),
        }


def _post_freshness(posts: list[RawPost], *, now_unix: float | None = None) -> float:
    if not posts:
        return 0.0
    now = float(now_unix or time.time())
    ages = []
    for p in posts:
        ts = p.created_at.timestamp() if p.created_at.tzinfo else p.created_at.replace(tzinfo=None).timestamp()
        ages.append(max(0.0, (now - ts) / 3600.0))
    youngest_h = min(ages) if ages else 0.0
    return round(math.exp(-youngest_h / 24.0), 4)


def compute_unified_relevance(
    posts: list[RawPost],
    *,
    channel_scores: dict[str, dict[str, Any]],
    evolution: EventEvolution,
    topic_row: dict[str, Any] | None,
    entity_hits: int,
    duplicate_similarity_pct: float | None,
    feedback_boost: float = 0.0,
) -> RelevanceBreakdown:
    """Heuristic blend — all inputs are observable in logs / draft_extras."""
    notes: list[str] = []
    freshness = _post_freshness(posts)

    rep_vals: list[float] = []
    for p in posts:
        key = str(p.channel_name or "").strip().lower()
        row = channel_scores.get(key) or {}
        rep_vals.append(float(row.get("score") or 0.5))
    source_reputation = round(sum(rep_vals) / max(1, len(rep_vals)), 4) if rep_vals else 0.5

    topic_momentum = 0.45
    if topic_row:
        c = int(topic_row.get("count") or 0)
        topic_momentum = max(0.2, min(1.0, 0.25 + 0.08 * min(c, 12)))
        notes.append("topic_memory_hit")

    entity_importance = max(0.15, min(1.0, 0.2 + 0.06 * min(entity_hits, 14)))

    novelty = 1.0 - max(0.0, min(1.0, evolution.continuity_score))
    if evolution.kind == "new":
        novelty = max(novelty, 0.55)
        notes.append("event_new")
    elif evolution.kind == "update":
        novelty = min(novelty, 0.45)
        notes.append("event_update")

    dup = float(duplicate_similarity_pct or 0.0) / 100.0
    duplicate_suppression = max(0.0, min(1.0, dup))
    if dup >= 0.88:
        notes.append("duplicate_high")

    editorial_preference_boost = max(0.0, min(0.25, feedback_boost))

    w = {
        "freshness": 0.22,
        "source_reputation": 0.18,
        "topic_momentum": 0.12,
        "entity_importance": 0.1,
        "novelty": 0.18,
        "duplicate_suppression": -0.35,
        "editorial_preference_boost": 0.15,
    }
    raw = (
        w["freshness"] * freshness
        + w["source_reputation"] * source_reputation
        + w["topic_momentum"] * topic_momentum
        + w["entity_importance"] * entity_importance
        + w["novelty"] * novelty
        + w["duplicate_suppression"] * duplicate_suppression
        + w["editorial_preference_boost"] * editorial_preference_boost
    )
    total = max(0.0, min(100.0, 50.0 + 48.0 * raw))

    return RelevanceBreakdown(
        freshness=freshness,
        source_reputation=source_reputation,
        topic_momentum=topic_momentum,
        entity_importance=entity_importance,
        novelty=novelty,
        duplicate_suppression=duplicate_suppression,
        editorial_preference_boost=editorial_preference_boost,
        weights=w,
        total=round(total, 2),
        notes=tuple(notes),
        policy_delta=0.0,
        policy_notes=(),
        policy_adjustments={},
    )


def apply_editorial_policy_to_relevance(
    rel: RelevanceBreakdown,
    policy: Any,
    *,
    topic_hint: str,
    combined_text: str,
    diversity: Any,
    topic_row: dict[str, Any] | None,
    evolution: EventEvolution,
) -> None:
    """Apply channel policy adjustments (mutates ``rel``; explainable deltas on 0–100 scale)."""
    import time

    from editorial.policy_models import ChannelEditorialPolicy

    if not isinstance(policy, ChannelEditorialPolicy):
        return
    hay = f"{topic_hint} {combined_text}".lower()
    adj: dict[str, float] = {}
    notes: list[str] = []
    delta = 0.0
    cap = float(policy.topic_affinity_boost_cap)
    for pref in policy.preferred_substrings:
        if pref and pref in hay:
            bump = min(cap, 0.04 + 0.02 * len(pref) / 10.0)
            delta += bump * 100.0 * float(policy.trend_sensitivity + 0.35)
            adj[f"affinity:{pref[:24]}"] = round(bump, 4)
            notes.append(f"policy_affinity:{pref[:40]}")
    for av in policy.avoided_substrings:
        if av and av in hay:
            pen = min(0.12, 0.03 + 0.01 * len(av))
            delta -= pen * 100.0
            adj[f"avoided:{av[:24]}"] = -round(pen, 4)
            notes.append(f"policy_avoided:{av[:40]}")
    if diversity is not None and int(getattr(diversity, "unique_channels", 99) or 0) < int(policy.min_unique_sources):
        pen = float(policy.low_diversity_penalty) * 90.0
        delta -= pen
        adj["low_source_diversity"] = -round(pen / 100.0, 4)
        notes.append("policy_low_source_diversity")
    if topic_row:
        cnt = int(topic_row.get("count") or 0)
        last_ts = float(topic_row.get("last_ts") or 0.0)
        age_h = max(0.0, (time.time() - last_ts) / 3600.0)
        if cnt >= 6 and age_h > 8.0:
            pen_pts = min(8.0, age_h * float(policy.stale_topic_penalty_weight) * float(policy.oversaturation_multiplier))
            delta -= pen_pts
            adj["stale_topic_memory"] = -round(pen_pts / 100.0, 4)
            notes.append("policy_stale_topic_penalty")
        if cnt >= 9:
            over = (float(policy.oversaturation_multiplier) - 1.0) * 2.5
            if over > 0:
                delta -= over
                adj["oversaturation_topic"] = -round(over / 100.0, 4)
                notes.append("policy_oversaturated_topic_penalty")
    for token, boost in policy.entity_boosts:
        if token and token in hay:
            add = min(4.5, float(boost) * 30.0)
            delta += add
            adj[f"entity_boost:{token[:20]}"] = round(add / 100.0, 4)
            notes.append(f"policy_entity_boost:{token[:30]}")
    if (
        policy.evergreen_update_suppress
        and evolution.kind == "update"
        and any(x in hay for x in ("weekly wrap", "week in review", "monthly", "calendar", "slow burn"))
    ):
        delta -= 3.0
        adj["evergreen_update_tone"] = -0.03
        notes.append("policy_evergreen_update_penalty")
    rel.policy_adjustments = adj
    rel.policy_notes = tuple(notes)
    rel.policy_delta = round(delta, 4)
    rel.total = max(0.0, min(100.0, float(rel.total) + delta))
