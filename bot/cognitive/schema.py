from __future__ import annotations

from bot.cognitive.types import CognitivePolicyDocument

DEFAULT_COGNITIVE_POLICY = CognitivePolicyDocument(
    policy_id="cognitive_default",
    version=1,
    evaluation_enabled=True,
    max_evaluations_per_hour=500,
    routing={
        "default_model": "gpt-4.1-mini",
        "premium_model": "gpt-4.1",
        "local_model": "local",
        "breaking_model": "gpt-4.1",
        "fallback_chain": ["gpt-4.1", "gpt-4.1-mini", "local"],
        "cheap_below_importance": 0.35,
        "premium_above_importance": 0.85,
    },
    learning={
        "max_delta_per_cycle": 0.05,
        "source_weight_bounds": [0.2, 2.0],
        "routing_adjustment_rate": 0.02,
    },
    cost={
        "daily_budget_usd": 25.0,
        "low_cost_mode_threshold": 0.9,
        "region_budgets": {},
    },
    simulation={
        "default_lane": "shadow",
        "promotion_min_score": 0.75,
    },
    memory={
        "max_entries": 50_000,
        "archive_after_days": 90,
        "temporal_buckets": ["hour", "day", "week"],
    },
)
