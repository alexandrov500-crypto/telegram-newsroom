from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.config import project_root
from bot.ops_forensics.replay import replay_publish_forensics
from bot.ops_forensics.repository import ForensicsRepository
from bot.ops_forensics.snapshots import capture_runtime_snapshot
from bot.storage.db import default_db_path


def export_incident_bundle(
    *,
    incident_id: str,
    publish_id: int | str | None = None,
    correlation_id: str | None = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Export immutable incident bundle for RCA."""
    repo = ForensicsRepository()
    root = project_root() / "var" / "ops" / "incident_bundles" / incident_id
    root.mkdir(parents=True, exist_ok=True)

    timeline = repo.query_timeline(
        correlation_id=correlation_id,
        publish_id=publish_id,
        limit=2000,
    )
    if not timeline and publish_id is not None:
        timeline = repo.query_timeline(publish_id=publish_id, limit=2000)

    (root / "timeline.json").write_text(
        json.dumps(timeline, indent=2, default=str),
        encoding="utf-8",
    )
    audit = repo.query_audit(
        correlation_id=correlation_id,
        publish_id=publish_id,
        limit=500,
    )
    (root / "audit.json").write_text(
        json.dumps(audit, indent=2, default=str),
        encoding="utf-8",
    )

    if publish_id is not None:
        replay = replay_publish_forensics(publish_id)
        (root / "publish_replay.json").write_text(
            json.dumps(replay, indent=2, default=str),
            encoding="utf-8",
        )

    snap = capture_runtime_snapshot()
    (root / "runtime_snapshot.json").write_text(
        json.dumps(snap, indent=2, default=str),
        encoding="utf-8",
    )

    baseline = repo.get_baseline()
    if baseline:
        (root / "runtime_baseline.json").write_text(
            json.dumps(baseline, indent=2, default=str),
            encoding="utf-8",
        )

    db_path = default_db_path()
    if log_path and log_path.is_file():
        shutil.copy2(log_path, root / "operator.log.tail")
    else:
        default_log = project_root() / "var" / "log" / "pilot-operator.log"
        if default_log.is_file():
            tail = default_log.read_text(encoding="utf-8", errors="replace")[-200_000:]
            (root / "operator.log.tail").write_text(tail, encoding="utf-8")

    summary = {
        "incident_id": incident_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "publish_id": str(publish_id) if publish_id is not None else None,
        "correlation_id": correlation_id,
        "timeline_events": len(timeline),
        "audit_entries": len(audit),
        "export_path": str(root),
    }
    (root / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )

    bundle_id = f"bundle_{incident_id}"
    repo.register_bundle(
        bundle_id=bundle_id,
        incident_id=incident_id,
        export_path=str(root),
        summary=summary,
    )
    return summary
