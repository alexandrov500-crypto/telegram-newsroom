from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode


class CanaryPublisher:
    """Rate-limited canary publishing with whitelist and safe hours."""

    def __init__(self, settings: ControlledLiveSettings) -> None:
        self.settings = settings

    def allow_publish(
        self,
        *,
        source: str,
        topic: str,
        state: dict[str, Any],
    ) -> tuple[bool, str]:
        mode = state.get("live_mode", self.settings.live_mode.value)
        if mode == LiveMode.SHADOW.value:
            return True, "shadow_ok"

        if self.settings.safe_hours_only and not self._in_safe_hours():
            return False, "outside_safe_hours"

        if mode == LiveMode.CANARY.value:
            allowed = self.settings.allowed_sources or self.settings.canary_whitelist_sources
            if allowed and source.strip().lower() not in allowed:
                return False, "source_not_whitelisted"
            if self.settings.canary_whitelist_topics and topic not in self.settings.canary_whitelist_topics:
                return False, "topic_not_whitelisted"
            bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
            if state.get("hour_bucket") != bucket:
                return True, "new_hour_bucket"
            try:
                from bot.editorial.flow_health.canary_balance import effective_canary_max_per_hour

                cap = int(effective_canary_max_per_hour().get("effective_cap") or self.settings.canary_max_per_hour)
            except Exception:
                cap = self.settings.canary_max_per_hour
            if int(state.get("publishes_this_hour", 0)) >= cap:
                return False, "canary_hourly_cap"

        return True, "ok"

    def _in_safe_hours(self) -> bool:
        hour = datetime.now(timezone.utc).hour
        start = self.settings.safe_hours_start
        end = self.settings.safe_hours_end
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end

    def status_html(self, state: dict[str, Any]) -> str:
        try:
            from bot.editorial.flow_health.canary_balance import effective_canary_max_per_hour

            cap = effective_canary_max_per_hour().get("effective_cap", self.settings.canary_max_per_hour)
        except Exception:
            cap = self.settings.canary_max_per_hour
        return (
            "<b>Canary status</b>\n"
            f"Mode: {state.get('live_mode', '?')}\n"
            f"Publishes this hour: {state.get('publishes_this_hour', 0)}"
            f"/{cap}\n"
            f"Safe hours: {self.settings.safe_hours_start}:00–{self.settings.safe_hours_end}:00 UTC"
            f" ({'enforced' if self.settings.safe_hours_only else 'advisory'})"
        )
