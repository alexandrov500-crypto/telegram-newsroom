"""Per-draft publish retry bounds and failure classification."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.reliability.failed_draft_recovery import max_retry_count
from utils.error_classifier import classify_runtime_error

_TRANSIENT_HINT = re.compile(
    r"(timeout|timed out|network|connection|floodwait|503|502|429|locked)",
    re.I,
)


@dataclass(frozen=True)
class PublishWatchdogVerdict:
    allowed: bool
    reason: str
    retry_count: int
    failure_class: str  # none | transient | permanent

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "retry_count": self.retry_count,
            "failure_class": self.failure_class,
        }


async def check_publish_watchdog(draft_id: int) -> PublishWatchdogVerdict:
    """Block publish when retry budget exhausted (dead-letter isolation)."""
    retry_count = 0
    last_error = ""
    try:
        from db.reliability_repository import get_failed_draft_row

        row = await get_failed_draft_row(draft_id)
        if row is not None:
            retry_count = int(row.retry_count or 0)
            last_error = str(row.last_error or "")
    except Exception:
        pass

    cap = max_retry_count()
    if retry_count >= cap:
        return PublishWatchdogVerdict(
            allowed=False,
            reason=f"max_retries_exceeded:{retry_count}>={cap}",
            retry_count=retry_count,
            failure_class="permanent",
        )
    return PublishWatchdogVerdict(
        allowed=True,
        reason="ok",
        retry_count=retry_count,
        failure_class=classify_publish_failure(last_error) if last_error else "none",
    )


def classify_publish_failure(reason: str) -> str:
    r = (reason or "").strip()
    if not r:
        return "none"
    if _TRANSIENT_HINT.search(r):
        return "transient"
    ce = classify_runtime_error(Exception(r))
    if ce.category in ("telegram", "network", "openai", "database", "scheduler") and ce.retryable:
        return "transient"
    if any(x in r.lower() for x in ("governance", "public_output_lock", "manual_review", "low_trust", "sensational")):
        return "permanent"
    return "permanent" if ce.category == "validation" else "transient"
