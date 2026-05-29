"""Resolve prompt fingerprints from settings (deterministic, migration-friendly)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ai.prompt_types import PromptSpec

CLUSTER_DRAFT_PROMPT_ID = "cluster_draft_json"


def fingerprint_cluster_draft(settings: Any) -> str:
    """
    Hash of policy knobs that affect system/user prompts for cluster drafting.
    Bump ``prompt_version`` in ``resolve_cluster_draft_prompt`` when semantics change.
    """
    payload = {
        "summary_style": str(getattr(settings, "summary_style", "")),
        "headline_mode": str(getattr(settings, "headline_mode", "")),
        "editorial_safety_enabled": bool(getattr(settings, "editorial_safety_enabled", True)),
        "digest_multi_post_enabled": bool(getattr(settings, "digest_multi_post_enabled", False)),
        "digest_cohesion_trigger_below": float(getattr(settings, "digest_cohesion_trigger_below", 0.11)),
        "quality_scoring_enabled": bool(getattr(settings, "quality_scoring_enabled", True)),
        "source_mentions_in_post": bool(getattr(settings, "source_mentions_in_post", False)),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def resolve_cluster_draft_prompt(settings: Any) -> PromptSpec:
    """Current cluster draft JSON prompt lineage."""
    fp = fingerprint_cluster_draft(settings)
    return PromptSpec(
        prompt_id=CLUSTER_DRAFT_PROMPT_ID,
        prompt_version="2026.05.28",
        fingerprint=fp,
        models_recommended=("gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"),
        metadata={"response_shape": "OpenAIClusterResponse"},
    )
