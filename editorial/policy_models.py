"""Typed editorial policy (per-channel overrides + defaults)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any


def _tuple_hours(pairs: list[Any]) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    for row in pairs or []:
        if isinstance(row, (list, tuple)) and len(row) == 2:
            a, b = int(row[0]), int(row[1])
            out.append((max(0, min(23, a)), max(0, min(23, b))))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class ChannelEditorialPolicy:
    """Channel-scoped knobs (explainable; all optional overrides merge onto default)."""

    preferred_substrings: tuple[str, ...] = ()
    avoided_substrings: tuple[str, ...] = ()
    relevance_suppress_below: float = 18.0
    relevance_cooldown_update_below: float = 42.0
    duplicate_signal_suppress_above: float = 0.75
    stale_topic_penalty_weight: float = 0.06
    trend_sensitivity: float = 0.5
    min_publish_interval_sec: float | None = None
    quiet_hours_local: tuple[tuple[int, int], ...] = ()
    headline_style_pref: str = "neutral"
    low_diversity_penalty: float = 0.07
    topic_affinity_boost_cap: float = 0.1
    oversaturation_multiplier: float = 1.0
    min_unique_sources: int = 1
    evergreen_update_suppress: bool = True
    entity_boosts: tuple[tuple[str, float], ...] = ()  # (normalized_substr, boost 0..0.15)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_substrings": list(self.preferred_substrings),
            "avoided_substrings": list(self.avoided_substrings),
            "relevance_suppress_below": self.relevance_suppress_below,
            "relevance_cooldown_update_below": self.relevance_cooldown_update_below,
            "duplicate_signal_suppress_above": self.duplicate_signal_suppress_above,
            "stale_topic_penalty_weight": self.stale_topic_penalty_weight,
            "trend_sensitivity": self.trend_sensitivity,
            "min_publish_interval_sec": self.min_publish_interval_sec,
            "quiet_hours_local": [list(x) for x in self.quiet_hours_local],
            "headline_style_pref": self.headline_style_pref,
            "low_diversity_penalty": self.low_diversity_penalty,
            "topic_affinity_boost_cap": self.topic_affinity_boost_cap,
            "oversaturation_multiplier": self.oversaturation_multiplier,
            "min_unique_sources": self.min_unique_sources,
            "evergreen_update_suppress": self.evergreen_update_suppress,
            "entity_boosts": [{"token": t, "boost": b} for t, b in self.entity_boosts],
        }


@dataclass(frozen=True, slots=True)
class EditorialPolicyBundle:
    schema_version: int = 1
    default_policy: ChannelEditorialPolicy = field(default_factory=ChannelEditorialPolicy)
    channel_policies: dict[str, ChannelEditorialPolicy] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default": self.default_policy.to_dict(),
            "channels": {k: v.to_dict() for k, v in sorted(self.channel_policies.items())},
        }


def channel_policy_from_dict(raw: dict[str, Any]) -> ChannelEditorialPolicy:
    """Build policy from JSON object (unknown keys ignored)."""
    qh = _tuple_hours(list(raw.get("quiet_hours_local") or []))
    eb_raw = raw.get("entity_boosts") or []
    eb_list: list[tuple[str, float]] = []
    if isinstance(eb_raw, list):
        for row in eb_raw:
            if isinstance(row, dict):
                t = str(row.get("token") or "").strip().lower()
                if t:
                    eb_list.append((t, max(0.0, min(0.2, float(row.get("boost") or 0.0)))))
    pref = tuple(str(x).lower() for x in (raw.get("preferred_substrings") or []) if str(x).strip())
    avoid = tuple(str(x).lower() for x in (raw.get("avoided_substrings") or []) if str(x).strip())
    kw: dict[str, Any] = {
        "preferred_substrings": pref,
        "avoided_substrings": avoid,
        "relevance_suppress_below": float(raw.get("relevance_suppress_below", 18.0)),
        "relevance_cooldown_update_below": float(raw.get("relevance_cooldown_update_below", 42.0)),
        "duplicate_signal_suppress_above": float(raw.get("duplicate_signal_suppress_above", 0.75)),
        "stale_topic_penalty_weight": float(raw.get("stale_topic_penalty_weight", 0.06)),
        "trend_sensitivity": max(0.0, min(1.0, float(raw.get("trend_sensitivity", 0.5)))),
        "min_publish_interval_sec": raw.get("min_publish_interval_sec"),
        "quiet_hours_local": qh,
        "headline_style_pref": str(raw.get("headline_style_pref") or "neutral").strip() or "neutral",
        "low_diversity_penalty": float(raw.get("low_diversity_penalty", 0.07)),
        "topic_affinity_boost_cap": float(raw.get("topic_affinity_boost_cap", 0.1)),
        "oversaturation_multiplier": max(0.2, min(3.0, float(raw.get("oversaturation_multiplier", 1.0)))),
        "min_unique_sources": max(1, min(8, int(raw.get("min_unique_sources", 1)))),
        "evergreen_update_suppress": bool(raw.get("evergreen_update_suppress", True)),
        "entity_boosts": tuple(eb_list),
    }
    if kw["min_publish_interval_sec"] is not None:
        kw["min_publish_interval_sec"] = max(0.0, float(kw["min_publish_interval_sec"]))
    allowed = {f.name for f in fields(ChannelEditorialPolicy)}
    return ChannelEditorialPolicy(**{k: v for k, v in kw.items() if k in allowed})


def merge_policies(base: ChannelEditorialPolicy, override: dict[str, Any] | None) -> ChannelEditorialPolicy:
    if not override:
        return base
    d = base.to_dict()
    known = {f.name for f in fields(ChannelEditorialPolicy)}
    for k, v in override.items():
        if k in known:
            d[k] = v
    return channel_policy_from_dict(d)
