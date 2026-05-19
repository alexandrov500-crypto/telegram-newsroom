from __future__ import annotations

import gzip
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.config import project_root
from bot.ops_observation.store import OpsObservationStore

logger = logging.getLogger(__name__)


def compact_pulse_files(
    *,
    keep_days: int = 30,
    dry_run: bool = False,
) -> dict[str, int]:
    """Roll old pulse jsonl into daily gz archives; remove source files."""
    store = OpsObservationStore()
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
    stats = {"files_archived": 0, "lines_compacted": 0, "files_removed": 0}
    archive_dir = project_root() / "var" / "archives" / "pulses"
    archive_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(store.pulses_dir.glob("*.jsonl")):
        try:
            day = datetime.fromisoformat(path.stem).date()
        except ValueError:
            continue
        if day >= cutoff:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        stats["lines_compacted"] += len(lines)
        if dry_run:
            stats["files_archived"] += 1
            continue
        out = archive_dir / f"{path.stem}.jsonl.gz"
        with gzip.open(out, "wt", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        path.unlink(missing_ok=True)
        stats["files_archived"] += 1
        stats["files_removed"] += 1
    return stats


def summarize_pulse_days_to_daily(*, keep_days: int = 7) -> int:
    """Aggregate recent pulse files into ops_lifecycle_daily summaries."""
    store = OpsObservationStore()
    written = 0
    by_day: dict[str, list[dict]] = defaultdict(list)
    for path in store.pulses_dir.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                by_day[path.stem].append(json.loads(line))
            except json.JSONDecodeError:
                continue
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=keep_days)
    for day, pulses in by_day.items():
        try:
            if datetime.fromisoformat(day).date() < cutoff:
                continue
        except ValueError:
            continue
        summary = {
            "pulse_count": len(pulses),
            "max_lag": max(float(p.get("event_loop_lag_max") or 0) for p in pulses) if pulses else 0,
            "anomaly_count": sum(len(p.get("anomalies") or []) for p in pulses),
        }
        _save_daily_summary(day, "pulses", summary)
        written += 1
    return written


def _save_daily_summary(day: str, category: str, summary: dict) -> None:
    from bot.ops_lifecycle.repository import LifecycleRepository
    from bot.storage.db import default_db_path

    LifecycleRepository(default_db_path()).save_daily_summary(day, category, summary)
