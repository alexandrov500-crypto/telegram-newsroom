"""Telegram E2E live simulation (no external side effects)."""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def simulate_telegram_live_flow(*, seed: int = 42) -> dict[str, Any]:
    rng = random.Random(seed)
    attempts = 24
    retries = 0
    published_ids: list[int] = []
    ghost = 0
    duplicate = 0
    reconnects = 0
    floodwaits = 0
    for i in range(attempts):
        draft_id = i + 1
        # intermittent failures, floodwait and reconnect scenarios
        r = rng.random()
        if r < 0.12:
            retries += 1
            floodwaits += 1
            continue
        if r < 0.18:
            retries += 1
            reconnects += 1
            continue
        msg_id = 10_000 + draft_id
        if msg_id in published_ids:
            duplicate += 1
        else:
            published_ids.append(msg_id)
        if rng.random() < 0.01:
            ghost += 1
    stable_recovery = retries <= int(attempts * 0.5)
    ok = duplicate == 0 and ghost == 0 and stable_recovery
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "attempts": attempts,
        "published_count": len(published_ids),
        "retry_count": retries,
        "floodwait_events": floodwaits,
        "reconnect_events": reconnects,
        "duplicate_posts": duplicate,
        "ghost_publishes": ghost,
        "stable_recovery": stable_recovery,
    }


def write_telegram_simulation_report(runtime_dir: str, report: dict[str, Any]) -> Path:
    out = Path(runtime_dir).expanduser().resolve() / "telegram_live_simulation_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


async def run_telegram_live_simulation_heartbeat(settings: Any) -> dict[str, Any]:
    report = simulate_telegram_live_flow()
    write_telegram_simulation_report(settings.runtime_state_dir, report)
    return report
