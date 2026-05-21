"""Build bounded incident tar.gz bundles (async-safe, no secrets)."""

from __future__ import annotations

import io
import json
import logging
import os
import platform
import socket
import tarfile
import time
from pathlib import Path
from typing import Any

from app.build_provenance import load_build_provenance, version_payload
from app.runtime_lifecycle import runtime_id, uptime_sec
from ops.log_ring import recent_log_lines
from ops.runtime_timeline import timeline_snapshot

logger = logging.getLogger(__name__)

_ENV_PREFIXES = (
    "NEWSROOM_",
    "HEALTH_",
    "TELEGRAM_",
    "OPENAI_",
    "RUNTIME_",
    "GIT_",
    "BUILD_",
    "DATABASE_",
    "BOT_",
    "ADMIN_",
    "JOB_QUEUE_",
    "QUALITY_",
    "EDITORIAL_",
    "DRY_RUN",
    "SOAK_TEST",
    "PIPELINE_",
)


def _safe_env_whitelist() -> dict[str, str]:
    from utils.security_redaction import redact_env_snapshot

    raw = {
        k: (os.environ.get(k) or "")[:120]
        for k in sorted(os.environ)
        if any(k.startswith(p) for p in _ENV_PREFIXES) or k in _ENV_PREFIXES
    }
    redacted = redact_env_snapshot(raw)
    sensitive = ("TOKEN", "KEY", "SECRET", "PASSWORD", "SESSION", "HASH")
    out: dict[str, str] = {}
    for k, v in redacted.items():
        if any(s in k.upper() for s in sensitive):
            out[k] = "***REDACTED***"
        else:
            out[k] = v[:80]
    return out


def collect_incident_payload(
    *,
    trigger: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.dependency_state import get_dependency_state
    from app.openai_circuit import get_openai_circuit
    from app.runtime_activity import activity_snapshot
    from app.runtime_metrics import export_merged_metrics

    prov = load_build_provenance()
    deps = get_dependency_state()
    try:
        health = deps.health_payload()
    except Exception as exc:
        health = {"error": repr(exc)}
    return {
        "trigger": trigger,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_id": runtime_id(),
        "uptime_sec": round(uptime_sec(), 2),
        "git_sha": prov.git_sha,
        "build_version": prov.build_version,
        "build_branch": prov.build_branch,
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "version": version_payload(polling_instance_id=deps.polling_instance_id or ""),
        "health": health,
        "metrics": export_merged_metrics(),
        "activity": activity_snapshot(),
        "circuit": get_openai_circuit().snapshot(),
        "timeline_tail": timeline_snapshot(limit=80),
        "recent_logs": recent_log_lines(limit=200),
        "detail": detail or {},
        "env_whitelist": _safe_env_whitelist(),
    }


def _write_tar_members(tf: tarfile.TarFile, payload: dict[str, Any]) -> None:
    def add_json(name: str, obj: Any) -> None:
        data = json.dumps(obj, indent=2, default=str).encode("utf-8")
        info = tarfile.TarInfo(name=name)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    add_json("manifest.json", {
        "trigger": payload.get("trigger"),
        "captured_at": payload.get("captured_at"),
        "runtime_id": payload.get("runtime_id"),
        "git_sha": payload.get("git_sha"),
        "build_version": payload.get("build_version"),
    })
    add_json("health.json", payload.get("health"))
    add_json("metrics.json", payload.get("metrics"))
    add_json("circuit.json", payload.get("circuit"))
    add_json("activity.json", payload.get("activity"))
    add_json("timeline.json", payload.get("timeline_tail"))
    add_json("detail.json", payload.get("detail"))
    add_json("env_whitelist.json", payload.get("env_whitelist"))
    add_json("version.json", payload.get("version"))
    logs = "\n".join(payload.get("recent_logs") or [])
    log_b = logs.encode("utf-8", errors="replace")[:500_000]
    info = tarfile.TarInfo(name="logs_recent.txt")
    info.size = len(log_b)
    tf.addfile(info, io.BytesIO(log_b))


def write_incident_bundle_sync(
    *,
    incidents_dir: Path,
    trigger: str,
    detail: dict[str, Any] | None = None,
    max_archive_bytes: int = 2_000_000,
) -> str | None:
    """Write tar.gz under incidents_dir; returns path or None on failure."""
    incidents_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    safe_trig = "".join(c if c.isalnum() or c in "-_" else "_" for c in trigger)[:48]
    name = f"incident_{safe_trig}_{ts}.tar.gz"
    path = incidents_dir / name
    payload = collect_incident_payload(trigger=trigger, detail=detail)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        _write_tar_members(tf, payload)
    data = buf.getvalue()
    if len(data) > max_archive_bytes:
        logger.warning(
            "incident.bundle.truncated_skipped size=%s max=%s trigger=%s",
            len(data),
            max_archive_bytes,
            trigger,
        )
        return None
    path.write_bytes(data)
    _apply_retention(incidents_dir)
    return str(path)


def _apply_retention(incidents_dir: Path) -> None:
    max_count = max(5, int(os.getenv("INCIDENT_RETENTION_COUNT", "24")))
    max_bytes = max(1_000_000, int(os.getenv("INCIDENT_RETENTION_MAX_BYTES", str(50_000_000))))
    files = sorted(incidents_dir.glob("incident_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = sum(p.stat().st_size for p in files)
    kept: list[Path] = []
    for p in files:
        if len(kept) >= max_count:
            p.unlink(missing_ok=True)
            continue
        if total > max_bytes and len(kept) >= 5:
            p.unlink(missing_ok=True)
            total -= p.stat().st_size
            continue
        kept.append(p)
        total = sum(x.stat().st_size for x in kept)
