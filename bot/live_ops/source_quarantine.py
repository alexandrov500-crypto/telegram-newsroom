from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceQuarantine:
    """Auto-cooldown sources after repeated bad posts."""

    def __init__(
        self,
        db_path: Path,
        *,
        bad_threshold: int = 3,
        window_hours: int = 24,
        cooldown_hours: int = 6,
        block_mode: str = "shadow",
    ) -> None:
        self._db_path = db_path
        self.bad_threshold = bad_threshold
        self.window_hours = window_hours
        self.cooldown_hours = cooldown_hours
        self.block_mode = block_mode  # shadow | block

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def record_bad_post(self, source: str) -> dict[str, Any] | None:
        if not source:
            return None
        key = source.strip().lower()
        now = datetime.now(timezone.utc)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT bad_count_24h, cooldown_until FROM live_source_quarantine WHERE source = ?",
                (key,),
            ).fetchone()
            count = 1
            if row:
                count = int(row[0]) + 1
                if row[1]:
                    try:
                        until = datetime.fromisoformat(str(row[1]).replace("Z", "+00:00"))
                        if now < until:
                            return {"source": key, "quarantined": True, "cooldown_until": row[1]}
                    except ValueError:
                        pass
            cooldown_until = None
            quarantined = False
            if count >= self.bad_threshold:
                until = now + timedelta(hours=self.cooldown_hours)
                cooldown_until = until.isoformat()
                quarantined = True
            conn.execute(
                """
                INSERT INTO live_source_quarantine (source, bad_count_24h, cooldown_until, mode, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    bad_count_24h = excluded.bad_count_24h,
                    cooldown_until = excluded.cooldown_until,
                    mode = excluded.mode,
                    updated_at = excluded.updated_at
                """,
                (key, count, cooldown_until, self.block_mode, _utcnow()),
            )
            conn.commit()
        if quarantined:
            return {
                "source": key,
                "quarantined": True,
                "bad_count": count,
                "cooldown_until": cooldown_until,
                "mode": self.block_mode,
            }
        return {"source": key, "quarantined": False, "bad_count": count}

    def is_quarantined(self, source: str) -> tuple[bool, str]:
        if not source:
            return False, ""
        key = source.strip().lower()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cooldown_until, mode FROM live_source_quarantine WHERE source = ?",
                (key,),
            ).fetchone()
        if not row or not row[0]:
            return False, ""
        try:
            until = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < until:
                return True, str(row[1] or self.block_mode)
            return False, ""
        except ValueError:
            return False, ""

    def list_active(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM live_source_quarantine WHERE cooldown_until IS NOT NULL",
            ).fetchall()
        out: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for r in rows:
            try:
                until = datetime.fromisoformat(str(r["cooldown_until"]).replace("Z", "+00:00"))
                if now < until:
                    out.append(dict(r))
            except ValueError:
                continue
        return out

    def status_html(self) -> str:
        active = self.list_active()
        lines = ["<b>Source quarantine</b>"]
        for a in active[:8]:
            lines.append(
                f"• {a['source']}: {a['mode']} until {str(a['cooldown_until'])[:16]}",
            )
        if len(lines) == 1:
            lines.append("No sources in cooldown.")
        return "\n".join(lines)
