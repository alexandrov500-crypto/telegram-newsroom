"""Bounded retention for incidents, journals, ledgers, snapshots."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ops.resilience.paths import retention_audit_path


def _ttl(name: str, default_sec: int) -> int:
    return int(os.getenv(name, str(default_sec)))


def _audit(runtime_dir: str, event: str, detail: dict[str, Any]) -> None:
    path = retention_audit_path(runtime_dir)
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "detail": detail,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass


def _prune_dir(
    directory: Path,
    *,
    pattern: str,
    max_files: int,
    max_bytes: int,
    max_age_sec: int,
) -> dict[str, Any]:
    if not directory.is_dir():
        return {"deleted": 0, "skipped": "missing"}
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime)
    now = time.time()
    deleted = 0
    freed = 0
    total = sum(p.stat().st_size for p in files)
    while files:
        victim = files[0]
        st = victim.stat()
        too_old = now - st.st_mtime > max_age_sec
        over_count = len(files) > max_files
        over_bytes = total > max_bytes
        if not (too_old or over_count or over_bytes):
            break
        try:
            total -= st.st_size
            victim.unlink()
            deleted += 1
            freed += st.st_size
        except OSError:
            break
        files.pop(0)
    return {"deleted": deleted, "freed_bytes": freed, "remaining": len(files)}


def run_lifecycle_retention(runtime_dir: str) -> dict[str, Any]:
    rt = Path(runtime_dir).expanduser().resolve()
    report: dict[str, Any] = {}

    report["incidents"] = _prune_dir(
        rt / "incidents",
        pattern="incident_*.tar.gz",
        max_files=int(os.getenv("RETENTION_INCIDENTS_MAX", "24")),
        max_bytes=_ttl("RETENTION_INCIDENTS_MAX_BYTES", 200_000_000),
        max_age_sec=_ttl("RETENTION_INCIDENTS_TTL_SEC", 86400 * 30),
    )
    report["full_snapshots"] = _prune_dir(
        rt / "full_snapshots",
        pattern="snap_*.tar.gz",
        max_files=int(os.getenv("RUNTIME_FULL_SNAPSHOT_MAX", "12")),
        max_bytes=_ttl("RUNTIME_FULL_SNAPSHOT_MAX_BYTES", 512_000_000),
        max_age_sec=_ttl("RETENTION_SNAPSHOT_TTL_SEC", 86400 * 14),
    )
    report["runtime_snapshots"] = _prune_dir(
        rt,
        pattern="snapshot_*.json",
        max_files=int(os.getenv("RUNTIME_SNAPSHOTS_MAX_COUNT", "50")),
        max_bytes=_ttl("RUNTIME_SNAPSHOTS_MAX_BYTES", 50_000_000),
        max_age_sec=_ttl("RETENTION_REPLAY_TTL_SEC", 86400 * 7),
    )

    from utils.metrics import inc

    for _ in range(int(report.get("incidents", {}).get("deleted", 0))):
        inc("retention_pruned_total")
    _audit(runtime_dir, "lifecycle_retention", report)
    return report
