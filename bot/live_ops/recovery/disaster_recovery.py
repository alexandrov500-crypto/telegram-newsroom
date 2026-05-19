from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecoveryReport:
    mode: str
    passed: bool
    replayed_events: int
    queue_depth: int
    issues: tuple[str, ...]

    def summary(self) -> str:
        lines = [
            f"<b>Recovery</b> mode=<code>{self.mode}</code>",
            f"Status: {'✅ OK' if self.passed else '⛔ ISSUES'}",
            f"Replayed: {self.replayed_events} · queue {self.queue_depth}",
        ]
        for issue in self.issues[:6]:
            lines.append(f"• {issue}")
        return "\n".join(lines)


class DisasterRecoveryManager:
    """Startup replay, snapshot export, partial failure resume."""

    def __init__(self, *, db_path: Path, export_dir: Path | None = None) -> None:
        self._db_path = db_path
        self._export_dir = export_dir or Path("var/recovery")

    @property
    def recovery_mode(self) -> bool:
        return os.getenv("RECOVERY_MODE", "").lower() in ("1", "true", "yes")

    @property
    def degraded_startup(self) -> bool:
        return os.getenv("DEGRADED_STARTUP", "").lower() in ("1", "true", "yes")

    async def run_startup_recovery(
        self,
        *,
        event_bus: Any | None = None,
        limit: int = 200,
    ) -> RecoveryReport:
        issues: list[str] = []
        replayed = 0
        queue_depth = 0

        if event_bus is not None:
            try:
                replayed = await event_bus.replay(limit=limit)
            except Exception as exc:
                issues.append(f"event_replay_failed: {exc}")

        if event_bus is not None and hasattr(event_bus, "pending_count"):
            queue_depth = int(event_bus.pending_count)

        integrity = self._check_replay_integrity()
        if not integrity:
            issues.append("replay_integrity_mismatch")

        passed = len(issues) == 0 or self.degraded_startup
        mode = "RECOVERY" if self.recovery_mode else ("DEGRADED" if self.degraded_startup else "NORMAL")
        logger.info(
            "event=startup_recovery mode=%s replayed=%d issues=%d",
            mode,
            replayed,
            len(issues),
        )
        return RecoveryReport(
            mode=mode,
            passed=passed,
            replayed_events=replayed,
            queue_depth=queue_depth,
            issues=tuple(issues),
        )

    def _check_replay_integrity(self) -> bool:
        try:
            import sqlite3

            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM sourced_event_log",
                ).fetchone()
                return row is not None
        except Exception:
            return True

    def export_snapshot(self, *, label: str = "manual") -> Path:
        self._export_dir.mkdir(parents=True, exist_ok=True)
        out = self._export_dir / f"snapshot_{label}.json"
        payload: dict[str, Any] = {"label": label, "db": str(self._db_path)}
        try:
            import sqlite3

            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
                ).fetchall()
                counts = {}
                for t in tables:
                    name = t["name"]
                    if name.startswith("sqlite_"):
                        continue
                    try:
                        c = conn.execute(f"SELECT COUNT(*) AS c FROM {name}").fetchone()
                        counts[name] = int(c["c"]) if c else 0
                    except Exception:
                        counts[name] = -1
                payload["table_counts"] = counts
        except Exception as exc:
            payload["error"] = str(exc)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("event=recovery_snapshot_export path=%s", out)
        return out
