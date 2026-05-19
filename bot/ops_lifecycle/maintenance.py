from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from bot.ops_lifecycle.archive import write_export_bundle
from bot.ops_lifecycle.entropy import compute_entropy_metrics
from bot.ops_lifecycle.repository import LifecycleRepository
from bot.ops_lifecycle.retention import RetentionEngine
from bot.ops_lifecycle.storage_report import build_ops_storage_payload
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("OPS_LIFECYCLE_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _interval_sec() -> int:
    try:
        return int(os.getenv("OPS_LIFECYCLE_INTERVAL_SEC", str(6 * 3600)))
    except ValueError:
        return 6 * 3600


def _vacuum_enabled() -> bool:
    raw = os.getenv("OPS_LIFECYCLE_VACUUM", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _backup_enabled() -> bool:
    raw = os.getenv("OPS_LIFECYCLE_BACKUP", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def run_maintenance_pass(
    db_path: Path | None = None,
    *,
    dry_run: bool = False,
    vacuum: bool | None = None,
    backup: bool | None = None,
) -> dict:
    """Single maintenance pass; safe to call from thread pool."""
    path = init_database(db_path or default_db_path())
    try:
        from bot.ops_resilience.context import should_suspend_archival

        if should_suspend_archival() and not dry_run:
            logger.info("event=lifecycle_maintenance_deferred reason=resilience_archival_suspend")
            return {"skipped": True, "reason": "resilience_archival_suspend"}
    except Exception:
        pass
    started = time.perf_counter()
    engine = RetentionEngine(path)
    do_vacuum = _vacuum_enabled() if vacuum is None else vacuum
    do_backup = _backup_enabled() if backup is None else backup
    if dry_run:
        do_vacuum = False
        do_backup = False

    report = engine.run(dry_run=dry_run, vacuum=do_vacuum, backup=do_backup)
    duration_ms = int((time.perf_counter() - started) * 1000)
    summary = report.to_dict()
    removed = sum(int(r.get("removed") or 0) for r in summary.get("results") or [])
    removed += int((summary.get("pulse") or {}).get("files_removed") or 0)
    removed += int((summary.get("storyline") or {}).get("events_removed") or 0)
    summary["entropy"] = compute_entropy_metrics(path)
    summary["entropy"]["last_maintenance_rows_removed"] = removed

    if not dry_run:
        now = datetime.now(timezone.utc).isoformat()
        repo = LifecycleRepository(path)
        prev = repo.get_state()
        repo.record_run("maintenance", summary, duration_ms=duration_ms)
        repo.update_state(
            last_maintenance_at=now,
            last_vacuum_at=now if report.vacuum else prev.get("last_vacuum_at"),
            last_backup_at=now if report.backup_path else prev.get("last_backup_at"),
            state_patch={
                "last_rows_removed": summary.get("entropy", {}).get(
                    "last_maintenance_rows_removed",
                ),
            },
        )
        try:
            write_export_bundle(path, build_ops_storage_payload(path))
        except Exception:
            pass

    logger.info(
        "event=lifecycle_maintenance_complete dry_run=%s duration_ms=%d vacuum=%s",
        dry_run,
        duration_ms,
        report.vacuum,
    )
    return summary


async def lifecycle_maintenance_loop(db_path: Path | None = None) -> None:
    """Background scheduler — never blocks publish path."""
    import asyncio

    path = db_path or default_db_path()
    interval = _interval_sec()
    logger.info("event=lifecycle_scheduler_started interval_sec=%d", interval)
    while True:
        if _enabled():
            try:
                await asyncio.to_thread(run_maintenance_pass, path, dry_run=False)
            except Exception:
                logger.exception("event=lifecycle_maintenance_failed")
        await asyncio.sleep(interval)
