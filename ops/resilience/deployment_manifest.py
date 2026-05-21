"""Immutable deployment manifest (reconstructable history, no secrets)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from app.build_provenance import load_build_provenance
from app.versioning import public_metadata
from ops.resilience.paths import deployment_manifest_path
from ops.resilience.snapshot import _config_fingerprint


def _dependency_snapshot() -> dict[str, str]:
    try:
        import aiogram
        import sqlalchemy

        return {
            "aiogram": getattr(aiogram, "__version__", "unknown"),
            "sqlalchemy": getattr(sqlalchemy, "__version__", "unknown"),
        }
    except Exception:
        return {}


def build_deployment_manifest(
    settings: Any,
    *,
    operational_mode: str = "production",
    governance_version: int = 1,
) -> dict[str, Any]:
    prov = load_build_provenance()
    return {
        "manifest_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": prov.git_sha,
        "build_version": prov.build_version,
        "build_branch": prov.build_branch,
        "build_timestamp": prov.build_timestamp,
        "deployment_profile": getattr(settings, "deployment_profile", "unknown"),
        "operational_mode": operational_mode,
        "config_fingerprint": _config_fingerprint(),
        "runtime_state_dir": getattr(settings, "runtime_state_dir", ""),
        "governance_version": governance_version,
        "compatibility": public_metadata(),
        "dependency_snapshot": _dependency_snapshot(),
        "flags": {
            "dry_run": bool(getattr(settings, "dry_run", False)),
            "soak_test": bool(getattr(settings, "soak_test", False)),
            "safe_mode": bool(getattr(settings, "safe_mode", False)),
            "redis_enabled": bool(getattr(settings, "redis_enabled", False)),
        },
    }


def write_deployment_manifest(settings: Any, *, operational_mode: str = "production") -> Path:
    manifest = build_deployment_manifest(settings, operational_mode=operational_mode)
    path = deployment_manifest_path(settings.runtime_state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(manifest, indent=2, sort_keys=True)
    path.write_text(raw, encoding="utf-8")
    sidecar = path.with_suffix(".json.sha256")
    sidecar.write_text(hashlib.sha256(raw.encode()).hexdigest(), encoding="utf-8")
    hist_path = path.parent / "deployment_manifest_history.jsonl"
    try:
        with hist_path.open("a", encoding="utf-8") as fh:
            fh.write(raw.replace("\n", "")[:4000] + "\n")
    except OSError:
        pass
    try:
        from ops.trust.evolution_journal import append_evolution_event

        append_evolution_event(
            settings.runtime_state_dir,
            event_type="deployment",
            summary=f"git={manifest.get('git_sha')}",
            detail={"build_version": manifest.get("build_version"), "config_fingerprint": manifest.get("config_fingerprint")},
        )
    except Exception:
        pass
    return path


def load_deployment_manifest(runtime_dir: str) -> dict[str, Any]:
    path = deployment_manifest_path(runtime_dir)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
