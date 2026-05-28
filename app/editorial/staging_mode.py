"""FINAL_STAGING_MODE — conservative publish gate before public launch."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.editorial.source_tiers import aggregate_source_tier

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StagingPublishVerdict:
    allowed: bool
    manual_review_required: bool
    reason: str
    audit_sample: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "manual_review_required": self.manual_review_required,
            "reason": self.reason,
            "audit_sample": self.audit_sample,
        }


def is_final_staging_mode(settings: Settings | None = None) -> bool:
    if settings is not None:
        return bool(getattr(settings, "final_staging_mode", False))
    return os.getenv("FINAL_STAGING_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


def _max_publishes_per_hour(settings: Settings | None) -> int:
    if settings is not None:
        return int(getattr(settings, "final_staging_max_publishes_per_hour", 6) or 6)
    try:
        return max(1, int(os.getenv("FINAL_STAGING_MAX_PUBLISHES_PER_HOUR", "6")))
    except ValueError:
        return 6


def _hourly_publish_count(runtime_dir: str | None) -> int:
    if not runtime_dir:
        return 0
    path = os.path.join(runtime_dir, "staging_publish_hour.json")
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        return 0
    window_start = float(data.get("window_start") or 0)
    if time.time() - window_start > 3600:
        return 0
    return int(data.get("count") or 0)


def record_staging_publish(runtime_dir: str | None) -> None:
    if not runtime_dir:
        return
    os.makedirs(runtime_dir, exist_ok=True)
    path = os.path.join(runtime_dir, "staging_publish_hour.json")
    now = time.time()
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError):
        data = {"window_start": now, "count": 0}
    if now - float(data.get("window_start") or 0) > 3600:
        data = {"window_start": now, "count": 0}
    data["count"] = int(data.get("count") or 0) + 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def evaluate_staging_publish_gate(
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    settings: Settings | None = None,
    operator_approved: bool = False,
    draft_id: int | None = None,
) -> StagingPublishVerdict:
    if not is_final_staging_mode(settings):
        return StagingPublishVerdict(True, False, "staging_off")

    tier = aggregate_source_tier(sources, runtime_dir=runtime_dir)
    hourly = _hourly_publish_count(runtime_dir)
    cap = _max_publishes_per_hour(settings)

    if tier.tier >= 3:
        if operator_approved:
            logger.info(
                "staging_mode tier3_operator_publish draft_id=%s tier=%s",
                draft_id,
                tier.tier,
            )
            return StagingPublishVerdict(True, False, "staging_tier3_operator_ok", audit_sample=True)
        return StagingPublishVerdict(False, True, "staging_tier3_manual_only")

    if hourly >= cap and not operator_approved:
        return StagingPublishVerdict(False, True, f"staging_hourly_cap:{hourly}/{cap}")

    audit = (draft_id or 0) % 7 == 0
    if audit:
        logger.info("staging_mode audit_sample draft_id=%s tier=%s", draft_id, tier.tier)
    return StagingPublishVerdict(True, False, "staging_tier12_ok", audit_sample=audit)
