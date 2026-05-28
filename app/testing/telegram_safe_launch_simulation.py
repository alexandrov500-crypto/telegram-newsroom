"""Telegram safe launch simulation — deterministic, zero real channel posts."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def simulate_telegram_safe_launch(*, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    attempts = 30
    retries = 0
    floodwaits = 0
    reconnects = 0
    partial_failures = 0
    published_ids: list[int] = []
    duplicate = 0
    ghost = 0
    events: list[dict[str, Any]] = []

    for i in range(attempts):
        draft_id = i + 1
        event: dict[str, Any] = {
            "attempt": i + 1,
            "draft_id": draft_id,
            "simulated": True,
            "real_telegram_post": False,
        }
        r = rng.random()
        if r < 0.10:
            retries += 1
            floodwaits += 1
            event["outcome"] = "floodwait_retry"
            events.append(event)
            log_event(logger, "telegram_safe_simulation.event", **event)
            continue
        if r < 0.16:
            retries += 1
            reconnects += 1
            event["outcome"] = "reconnect_retry"
            events.append(event)
            log_event(logger, "telegram_safe_simulation.event", **event)
            continue
        if r < 0.20:
            partial_failures += 1
            event["outcome"] = "partial_publish_failure"
            events.append(event)
            log_event(logger, "telegram_safe_simulation.event", **event)
            continue

        msg_id = 20_000 + draft_id
        if msg_id in published_ids:
            duplicate += 1
            event["outcome"] = "duplicate_blocked"
        else:
            published_ids.append(msg_id)
            event["outcome"] = "publish_success"
            event["telegram_post_id"] = msg_id
        if rng.random() < 0.005:
            ghost += 1
            event["ghost_detected"] = True
        events.append(event)
        log_event(logger, "telegram_safe_simulation.event", **event)

    stable_recovery = retries <= int(attempts * 0.5)
    ok = duplicate == 0 and ghost == 0 and stable_recovery
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
        "zero_real_posts": True,
        "seed": seed,
        "ok": ok,
        "attempts": attempts,
        "published_count": len(published_ids),
        "retry_count": retries,
        "floodwait_events": floodwaits,
        "reconnect_events": reconnects,
        "partial_failures": partial_failures,
        "duplicate_posts": duplicate,
        "ghost_publishes": ghost,
        "stable_recovery": stable_recovery,
        "events_sample": events[:20],
    }


def write_telegram_safe_simulation_report(
    report: dict[str, Any],
    *,
    runtime_dir: str | None = None,
) -> Path:
    rd = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).expanduser().resolve()
    out = rd / "telegram_safe_simulation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    events_path = rd / "telegram_safe_simulation_events.jsonl"
    lines = [json.dumps(ev, ensure_ascii=False) for ev in (report.get("events_sample") or [])]
    events_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out
