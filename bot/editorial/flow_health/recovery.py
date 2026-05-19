from __future__ import annotations

import logging
import os
import time
from typing import Any

from bot.editorial.flow_health.funnel import funnel_summary, record_funnel
from bot.editorial.flow_health.floor import is_publish_floor_active

logger = logging.getLogger(__name__)

_last_recovery_at: float = 0.0


def _recovery_enabled() -> bool:
    return os.getenv("PUBLISH_RECOVERY_DIGEST_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def should_run_recovery_digest() -> bool:
    if not _recovery_enabled() or not is_publish_floor_active():
        return False
    try:
        from bot.editorial.flow_health.digest_discipline import digest_recovery_allowed

        if not digest_recovery_allowed():
            return False
    except Exception:
        pass
    global _last_recovery_at
    try:
        cooldown = float(os.getenv("PUBLISH_RECOVERY_DIGEST_COOLDOWN_SEC", "14400"))
    except ValueError:
        cooldown = 14400.0
    if time.monotonic() - _last_recovery_at < cooldown:
        return False
    starvation = funnel_summary().get("starvation") or {}
    if not starvation.get("detected"):
        return False
    if int(starvation.get("published", 0)) >= 2:
        return False
    try:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cadence = compute_cadence_health()
        if float(cadence.get("cadence_health") or 1.0) >= 0.85:
            return False
    except Exception:
        pass
    return True


async def try_recovery_digest(digest_service: Any) -> dict[str, Any] | None:
    """Digest-first recovery — piggybacks existing DigestService, no new loop."""
    if not should_run_recovery_digest():
        return None
    global _last_recovery_at
    try:
        from bot.storage.digest_repository import DIGEST_HOURLY

        result = await digest_service.run_digest(
            DIGEST_HOURLY,
            publish=True,
            force_since=None,
        )
        _last_recovery_at = time.monotonic()
        try:
            from bot.editorial.flow_health.digest_discipline import note_digest_recovery_success

            note_digest_recovery_success()
        except Exception:
            pass
        record_funnel("PUBLISHED", rejection_reason="recovery_digest")
        logger.info(
            "event=recovery_digest_complete published=%s items=%s",
            result.published,
            result.item_count,
        )
        try:
            from bot.operator_ux.service import record_attention_signal
            from bot.operator_ux.severity import AttentionSeverity

            record_attention_signal(
                category="publish_recovery",
                title="Night brief published (starvation recovery)",
                severity=AttentionSeverity.INFO,
                detail=str(starvation_reason()),
            )
        except Exception:
            pass
        return {
            "recovery_digest": True,
            "item_count": result.item_count,
            "published": result.published,
        }
    except Exception:
        logger.debug("event=recovery_digest_failed")
        return None


def starvation_reason() -> str:
    s = funnel_summary().get("starvation") or {}
    return str(s.get("reason") or "unknown")
