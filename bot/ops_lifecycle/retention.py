from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.ops_lifecycle.compaction import compact_pulse_files, summarize_pulse_days_to_daily
from bot.ops_lifecycle.policies import ArtifactPolicy, default_policies
from bot.ops_lifecycle.storyline_lifecycle import archive_idle_storylines
from bot.storage.db import init_database

logger = logging.getLogger(__name__)


@dataclass
class RetentionResult:
    policy: str
    action: str
    rows_before: int = 0
    rows_after: int = 0
    removed: int = 0
    archived: int = 0
    detail: str = ""


@dataclass
class MaintenanceReport:
    dry_run: bool
    results: list[RetentionResult] = field(default_factory=list)
    pulse: dict[str, int] = field(default_factory=dict)
    storyline: dict[str, int] = field(default_factory=dict)
    vacuum: bool = False
    backup_path: str | None = None
    integrity_ok: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "results": [r.__dict__ for r in self.results],
            "pulse": self.pulse,
            "storyline": self.storyline,
            "vacuum": self.vacuum,
            "backup_path": self.backup_path,
            "integrity_ok": self.integrity_ok,
            "errors": self.errors,
        }


class RetentionEngine:
    def __init__(self, db_path: Path, *, policies: list[ArtifactPolicy] | None = None) -> None:
        self._db_path = init_database(db_path)
        self._policies = policies or default_policies()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=30)

    def _cutoff(self, days: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    def _count(self, conn: sqlite3.Connection, table: str) -> int:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:
            return 0

    def _prune_table(
        self,
        conn: sqlite3.Connection,
        policy: ArtifactPolicy,
        *,
        dry_run: bool,
        extra_where: str = "",
        params: tuple = (),
    ) -> RetentionResult:
        if not policy.table:
            return RetentionResult(policy.name, policy.action)
        before = self._count(conn, policy.table)
        cutoff = self._cutoff(policy.retention_days)
        where = f"{policy.time_column} < ?"
        if extra_where:
            where += f" AND ({extra_where})"
        args: tuple = (cutoff, *params)
        if dry_run:
            try:
                removed = conn.execute(
                    f"SELECT COUNT(*) FROM {policy.table} WHERE {where}",
                    args,
                ).fetchone()[0]
            except sqlite3.OperationalError:
                removed = 0
            return RetentionResult(
                policy.name,
                policy.action,
                rows_before=before,
                rows_after=before - int(removed),
                removed=int(removed),
                detail=f"dry-run cutoff {policy.retention_days}d",
            )
        try:
            conn.execute(f"DELETE FROM {policy.table} WHERE {where}", args)
            after = self._count(conn, policy.table)
            return RetentionResult(
                policy.name,
                policy.action,
                rows_before=before,
                rows_after=after,
                removed=before - after,
            )
        except sqlite3.OperationalError as exc:
            return RetentionResult(policy.name, policy.action, detail=str(exc)[:80])

    def _summarize_timeline(self, conn: sqlite3.Connection, policy: ArtifactPolicy, *, dry_run: bool) -> RetentionResult:
        info_cutoff = self._cutoff(policy.retention_days)
        crit_days = policy.keep_critical_days or 365
        crit_cutoff = self._cutoff(crit_days)
        before = self._count(conn, policy.table or "live_incident_timeline")
        if dry_run:
            return RetentionResult(
                policy.name,
                "summarize",
                rows_before=before,
                detail="timeline: info>30d summarize, critical retained",
            )
        try:
            rows = conn.execute(
                """
                SELECT date(timestamp) AS d, severity, COUNT(*) AS c
                FROM live_incident_timeline
                WHERE timestamp < ? AND severity NOT IN ('critical', 'error')
                GROUP BY d, severity
                """,
                (info_cutoff,),
            ).fetchall()
            for day, sev, count in rows:
                from bot.ops_lifecycle.repository import LifecycleRepository

                LifecycleRepository(self._db_path).save_daily_summary(
                    str(day),
                    f"timeline_{sev}",
                    {"event_count": count},
                )
            conn.execute(
                """
                DELETE FROM live_incident_timeline
                WHERE timestamp < ? AND severity NOT IN ('critical', 'error')
                """,
                (info_cutoff,),
            )
            conn.execute(
                """
                DELETE FROM live_incident_timeline
                WHERE timestamp < ? AND severity IN ('critical', 'error')
                """,
                (crit_cutoff,),
            )
            after = self._count(conn, "live_incident_timeline")
            return RetentionResult(
                policy.name,
                "summarize",
                rows_before=before,
                rows_after=after,
                removed=before - after,
            )
        except sqlite3.OperationalError as exc:
            return RetentionResult(policy.name, "summarize", detail=str(exc)[:80])

    def run(self, *, dry_run: bool = True, vacuum: bool = False, backup: bool = False) -> MaintenanceReport:
        report = MaintenanceReport(dry_run=dry_run)
        from bot.ops_lifecycle.archive import backup_database, verify_sqlite_integrity

        report.integrity_ok = verify_sqlite_integrity(self._db_path)
        if backup and not dry_run:
            bp = backup_database(self._db_path)
            report.backup_path = str(bp) if bp else None

        for policy in self._policies:
            try:
                if policy.name == "runtime_pulses":
                    report.pulse = compact_pulse_files(
                        keep_days=policy.retention_days,
                        dry_run=dry_run,
                    )
                    if not dry_run:
                        summarize_pulse_days_to_daily(keep_days=7)
                    continue
                if policy.table == "live_incident_timeline" and policy.action == "summarize":
                    with self._conn() as conn:
                        if not dry_run:
                            conn.commit()
                        r = self._summarize_timeline(conn, policy, dry_run=dry_run)
                        if not dry_run:
                            conn.commit()
                    report.results.append(r)
                    continue
                if policy.table == "editorial_story_events":
                    report.storyline = archive_idle_storylines(
                        self._db_path,
                        idle_days=policy.retention_days,
                        dry_run=dry_run,
                    )
                    continue
                if policy.table and policy.action in ("compact", "rotate", "expire", "summarize", "archive"):
                    with self._conn() as conn:
                        r = self._prune_table(conn, policy, dry_run=dry_run)
                        if not dry_run:
                            conn.commit()
                    report.results.append(r)
            except Exception as exc:
                report.errors.append(f"{policy.name}:{exc}")
                logger.debug("event=retention_policy_failed name=%s", policy.name)

        if vacuum and not dry_run:
            try:
                with self._conn() as conn:
                    conn.execute("VACUUM")
                report.vacuum = True
            except Exception as exc:
                report.errors.append(f"vacuum:{exc}")

        return report
