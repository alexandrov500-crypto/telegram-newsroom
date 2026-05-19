from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any


def analyze_operator_workflow(
    audit_rows: list[dict[str, Any]],
    *,
    hours: int = 168,
) -> dict[str, Any]:
    """Command usage, overrides, freeze/resume from operational audit log."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    command_counts: Counter[str] = Counter()
    override_actions: Counter[str] = Counter()
    freeze_count = 0
    resume_count = 0
    mark_good = 0
    mark_bad = 0
    dashboard_views = 0

    for row in audit_rows:
        ts_raw = row.get("timestamp") or row.get("created_at")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < since:
                    continue
            except ValueError:
                pass

        action = str(row.get("action") or "")
        command_counts[action] += 1

        if action in ("mark_good_post", "mark_bad_post"):
            if "good" in action:
                mark_good += 1
            else:
                mark_bad += 1
            override_actions[action] += 1
        elif "override" in action.lower() or "reject" in action.lower():
            override_actions[action] += 1
        elif "freeze" in action.lower():
            freeze_count += 1
        elif "resume" in action.lower():
            resume_count += 1
        elif "dashboard" in action.lower() or action == "live_dashboard":
            dashboard_views += 1

    top_commands = command_counts.most_common(12)
    return {
        "window_hours": hours,
        "command_usage": dict(top_commands),
        "override_frequency": sum(override_actions.values()),
        "mark_good": mark_good,
        "mark_bad": mark_bad,
        "freeze_events": freeze_count,
        "resume_events": resume_count,
        "dashboard_interactions": dashboard_views,
        "attention_commands": sum(
            command_counts.get(c, 0)
            for c in ("operator_digest", "attention_queue", "trust_calibration", "weekly_review")
        ),
    }
