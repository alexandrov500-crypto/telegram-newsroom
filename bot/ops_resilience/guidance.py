from __future__ import annotations

from typing import Any

from bot.ops_resilience.types import OperationalPosture


def build_recovery_guidance(
    *,
    posture: str,
    dependencies: dict[str, dict[str, Any]],
    failure_budgets: dict[str, Any],
    forecast: dict[str, Any],
    degradation_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Operator-facing recovery steps — not raw alerts."""
    guidance: list[dict[str, Any]] = []

    def _add(
        title: str,
        cause: str,
        action: str,
        *,
        escalation: str = "info",
    ) -> None:
        guidance.append(
            {
                "title": title,
                "probable_cause": cause,
                "recommended_action": action,
                "escalation": escalation,
            },
        )

    rss = dependencies.get("rss_ingestion", {})
    if rss.get("band") in ("degraded", "unstable"):
        _add(
            "RSS backlog risk",
            "Feed fetch duration elevated or ingestion lagging",
            "Freeze ingestion expansion and observe for 15m. Check /live_status and feed health.",
            escalation="important",
        )

    tg = dependencies.get("telegram_api", {})
    if tg.get("band") in ("degraded", "unstable", "critical"):
        _add(
            "Telegram API stress",
            tg.get("last_error") or "Connectivity or rate limits",
            "Reduce publish rate; verify bot token and channel permissions. Use /pause if errors persist.",
            escalation="critical" if tg.get("band") == "critical" else "important",
        )

    if failure_budgets.get("recovery_storm"):
        _add(
            "Recovery storm",
            "Multiple recovery attempts in short window",
            "Enter observation mode: pause non-essential loops, review /resilience_status, avoid config changes for 10m.",
            escalation="critical",
        )

    if forecast.get("pressure_level") in ("elevated", "critical"):
        _add(
            "Pressure forecast",
            forecast.get("summary", "Operational pressure rising"),
            forecast.get("safe_next_step", "Monitor queue and lag for 15m before resuming full publish rate."),
            escalation="important",
        )

    for action in degradation_actions:
        cond = action.get("condition")
        if cond == "disk_pressure":
            _add(
                "Disk pressure",
                "Archive or DB growth approaching limits",
                "Run /ops_storage; defer archival until space recovers. Consider manual prune.",
                escalation="important",
            )
        elif cond == "event_loop_lag":
            _add(
                "Event loop lag",
                "Background work competing with critical path",
                "Analytics paused automatically. Wait for lag to drop below 0.4s before heavy operator commands.",
            )

    if posture == OperationalPosture.OBSERVATION_ONLY.value:
        _add(
            "Observation only",
            "Repeated failures or critical dependency loss",
            "Safe next step: /pause live publishing, review incidents, do not tune scoring until stable.",
            escalation="critical",
        )
    elif posture == OperationalPosture.STABLE.value and not guidance:
        _add(
            "Stable operations",
            "No active degradation triggers",
            "Continue canary cadence; routine /operator_digest is sufficient.",
        )

    return guidance[:12]
