from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


@dataclass
class StartupCheck:
    name: str
    passed: bool
    detail: str
    critical: bool = True


@dataclass
class ControlledLiveStartupReport:
    passed: bool
    forced_shadow: bool
    checks: list[StartupCheck] = field(default_factory=list)

    def critical_failures(self) -> list[StartupCheck]:
        return [c for c in self.checks if c.critical and not c.passed]


class ControlledLiveStartupValidator:
    """Validate runtime before allowing live publish."""

    def __init__(self, db_path: Path, settings: ControlledLiveSettings) -> None:
        self.db_path = db_path
        self.settings = settings

    async def validate(self) -> ControlledLiveStartupReport:
        checks: list[StartupCheck] = []
        checks.append(self._check_db())
        checks.append(self._check_live_tables())
        checks.append(self._check_telegram_config())
        checks.append(self._check_live_mode())
        checks.append(self._check_rollback_repo())
        checks.append(await self._check_openai())
        checks.append(self._check_event_bus())
        critical_failed = any(c.critical and not c.passed for c in checks)
        if critical_failed:
            runtime_state.shadow_publish_only = True
            if self.settings.live_mode != LiveMode.SHADOW:
                logger.warning("event=controlled_live_forced_shadow startup_checks_failed")
        return ControlledLiveStartupReport(
            passed=not critical_failed,
            forced_shadow=critical_failed,
            checks=checks,
        )

    def _check_db(self) -> StartupCheck:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            return StartupCheck("db", True, "sqlite ok")
        except Exception as exc:
            return StartupCheck("db", False, str(exc), critical=True)

    def _check_live_tables(self) -> StartupCheck:
        required = (
            "live_channel_state",
            "live_publish_trace",
            "live_source_quarantine",
            "live_metrics_snapshots",
        )
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            for table in required:
                row = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not row:
                    conn.close()
                    return StartupCheck(
                        "live_tables",
                        False,
                        f"missing {table}",
                        critical=True,
                    )
            conn.close()
            return StartupCheck("live_tables", True, "all tables present")
        except Exception as exc:
            return StartupCheck("live_tables", False, str(exc), critical=True)

    def _check_telegram_config(self) -> StartupCheck:
        import os

        channel = os.getenv("LIVE_PUBLIC_CHANNEL_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
        token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            return StartupCheck("telegram", False, "BOT_TOKEN missing", critical=True)
        if not channel:
            return StartupCheck("telegram", False, "channel id missing", critical=True)
        return StartupCheck("telegram", True, f"channel configured")

    def _check_live_mode(self) -> StartupCheck:
        if self.settings.live_mode == LiveMode.AUTONOMOUS_LIVE:
            return StartupCheck(
                "live_mode",
                False,
                "autonomous_live blocked during pilot",
                critical=True,
            )
        return StartupCheck("live_mode", True, self.settings.live_mode.value)

    def _check_rollback_repo(self) -> StartupCheck:
        if not self.settings.enable_rollback:
            return StartupCheck("rollback", True, "rollback disabled by env")
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.execute("SELECT id FROM live_channel_publish_log LIMIT 1")
            conn.close()
            return StartupCheck("rollback", True, "audit log reachable")
        except Exception as exc:
            return StartupCheck("rollback", False, str(exc), critical=False)

    async def _check_openai(self) -> StartupCheck:
        import os

        if not os.getenv("OPENAI_API_KEY"):
            return StartupCheck("openai", False, "OPENAI_API_KEY missing", critical=False)
        return StartupCheck("openai", True, "key present")

    def _check_event_bus(self) -> StartupCheck:
        try:
            from bot.live_ops.context_holder import get_live_ops

            lo = get_live_ops()
            if lo is None:
                return StartupCheck("event_bus", True, "live_ops optional offline")
            pending = lo.event_bus.pending_count
            dlq = lo.event_bus.dead_letter_count
            if dlq > 100:
                return StartupCheck(
                    "event_bus",
                    False,
                    f"dlq={dlq}",
                    critical=False,
                )
            return StartupCheck("event_bus", True, f"pending={pending} dlq={dlq}")
        except Exception as exc:
            return StartupCheck("event_bus", False, str(exc), critical=False)

    def summary_html(self, report: ControlledLiveStartupReport) -> str:
        lines = [
            "<b>Controlled live startup</b>",
            f"Passed: {'yes' if report.passed else 'no'}",
            f"Forced shadow: {'yes' if report.forced_shadow else 'no'}",
        ]
        for c in report.checks:
            mark = "✓" if c.passed else "✗"
            lines.append(f"{mark} {c.name}: {c.detail}")
        return "\n".join(lines)
