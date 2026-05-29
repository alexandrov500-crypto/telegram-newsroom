"""Cross-post orchestration — duplicate prevention + timing."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.flywheel.distribution_router import DistributionSurface, RoutingDecision
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossPostPlan:
    primary_channel_id: int
    mirror_digest: bool
    digest_channel_id: int | None
    dedupe_key: str
    skip: bool
    reason: str


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "cross_post_dedupe.json"


def plan_cross_post(
    settings: Any,
    decision: RoutingDecision,
    *,
    runtime_dir: str,
    content_hash: str,
) -> CrossPostPlan:
    digest_ch = None
    raw = __import__("os").getenv("TELEGRAM_DIGEST_CHANNEL_ID", "").strip()
    if raw:
        try:
            digest_ch = int(raw)
        except ValueError:
            digest_ch = None

    p = _state_path(runtime_dir)
    try:
        seen = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {"keys": []}

    keys = list(seen.get("keys") or [])
    now = time.time()
    keys = [k for k in keys if isinstance(k, dict) and now - float(k.get("ts") or 0) < 86400]

    if any(k.get("hash") == content_hash for k in keys):
        return CrossPostPlan(
            int(decision.channel_id),
            False,
            digest_ch,
            content_hash,
            True,
            "duplicate_24h",
        )

    if decision.surface == DistributionSurface.DISCARD:
        return CrossPostPlan(main_id(settings), False, digest_ch, content_hash, True, decision.reason)

    mirror = decision.also_digest and digest_ch and digest_ch != int(decision.channel_id)
    return CrossPostPlan(
        int(decision.channel_id),
        mirror,
        digest_ch if mirror else None,
        content_hash,
        False,
        decision.reason,
    )


def main_id(settings: Any) -> int:
    return int(getattr(settings, "target_channel_id", 0) or 0)


async def execute_digest_mirror(
    bot: Any,
    *,
    digest_channel_id: int,
    html: str,
) -> int | None:
    if not digest_channel_id or not html:
        return None
    try:
        from aiogram.enums import ParseMode

        msg = await bot.send_message(
            chat_id=digest_channel_id,
            text=html[:4000],
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return int(msg.message_id)
    except Exception as exc:
        log_event(logger, "flywheel.digest_mirror_failed", error=repr(exc)[:200])
        return None


def record_cross_post(runtime_dir: str, content_hash: str) -> None:
    p = _state_path(runtime_dir)
    try:
        seen = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        seen = {"keys": []}
    keys = list(seen.get("keys") or [])
    keys.insert(0, {"hash": content_hash, "ts": time.time()})
    seen["keys"] = keys[:200]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seen), encoding="utf-8")


async def log_distribution_event(
    *,
    draft_id: int | None,
    decision: RoutingDecision,
    content_hash: str,
    mirrored_digest: bool = False,
) -> None:
    from datetime import UTC, datetime

    from db.models import DistributionFlywheelLog
    from db.session import session_scope

    async with session_scope() as session:
        session.add(
            DistributionFlywheelLog(
                draft_id=draft_id,
                surface=decision.surface.value,
                channel_id=int(decision.channel_id),
                reason=decision.reason[:64],
                content_hash=content_hash[:24],
                mirrored_digest=1 if mirrored_digest else 0,
                created_at=datetime.now(UTC),
            )
        )
