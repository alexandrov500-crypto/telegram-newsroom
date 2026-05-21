"""Deployment self-checks: fail-fast vs degraded warnings."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.versioning import RUNTIME_STATE_SCHEMA_VERSION, public_metadata
from editorial.governance.paths import governance_rules_path
from editorial.governance.policies_engine import load_governance_rules
from editorial.intelligence_store import editorial_policies_path, load_json
from ops.resilience.migrations import apply_runtime_migrations
from ops.resilience.publish_journal import find_inflight
from ops.resilience.snapshot import SNAPSHOT_FORMAT_VERSION

logger = logging.getLogger(__name__)


class StartupValidationResult:
    def __init__(self) -> None:
        self.fatal: list[str] = []
        self.warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return not self.fatal

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fatal": list(self.fatal),
            "warnings": list(self.warnings),
            "compatibility": public_metadata(),
        }


def _check_writable(runtime_dir: Path, result: StartupValidationResult) -> None:
    for sub in ("", "editorial", "locks", "full_snapshots", "incidents"):
        d = runtime_dir / sub if sub else runtime_dir
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            result.fatal.append(f"runtime_dir not writable ({d}): {exc}")


def _check_policy_json(runtime_dir: str, result: StartupValidationResult) -> None:
    pol_path = editorial_policies_path(runtime_dir)
    if pol_path.is_file():
        try:
            data = json.loads(pol_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                result.warnings.append("editorial_policies.json: expected object")
        except (OSError, json.JSONDecodeError) as exc:
            result.fatal.append(f"editorial_policies.json invalid: {exc}")
    rules = load_governance_rules(runtime_dir)
    if not isinstance(rules.get("rules"), list):
        result.warnings.append("governance_rules: missing rules array")
    gr_path = governance_rules_path(runtime_dir)
    if gr_path.is_file():
        try:
            json.loads(gr_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.fatal.append(f"governance_rules.json invalid: {exc}")


def _check_snapshot_compat(runtime_dir: str, result: StartupValidationResult) -> None:
    snap_dir = Path(runtime_dir) / "full_snapshots"
    if not snap_dir.is_dir():
        return
    latest = sorted(snap_dir.glob("snap_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not latest:
        return
    result.warnings.append(f"full_snapshots_present: {len(latest)} archives (format v{SNAPSHOT_FORMAT_VERSION})")


def _check_publish_recovery(runtime_dir: str, result: StartupValidationResult) -> None:
    inflight = find_inflight(runtime_dir, max_age_sec=3600.0)
    if inflight:
        result.warnings.append(f"publish_journal_inflight: {len(inflight)} entries (review before publish)")


def run_startup_integrity_checks(settings: Any) -> StartupValidationResult:
    result = StartupValidationResult()
    rt = Path(settings.runtime_state_dir).expanduser().resolve()
    _check_writable(rt, result)
    _check_policy_json(str(rt), result)
    _check_snapshot_compat(str(rt), result)
    _check_publish_recovery(str(rt), result)

    if int(os.getenv("RUNTIME_STATE_SCHEMA_VERSION", str(RUNTIME_STATE_SCHEMA_VERSION))) > RUNTIME_STATE_SCHEMA_VERSION:
        result.fatal.append("RUNTIME_STATE_SCHEMA_VERSION env newer than runtime binary")

    try:
        mig = apply_runtime_migrations(str(rt))
        if mig.get("applied_now"):
            result.warnings.append(f"migrations_applied: {[x['migration'] for x in mig['applied_now']]}")
    except Exception as exc:
        result.fatal.append(f"runtime_migrations_failed: {exc}")

    queue_prefix = getattr(settings, "job_queue_prefix", "newsroom")
    if not queue_prefix or len(queue_prefix) > 64:
        result.fatal.append("job_queue_prefix invalid")

    if getattr(settings, "redis_enabled", False) and not getattr(settings, "redis_url", "").strip():
        result.fatal.append("REDIS_ENABLED without REDIS_URL")

    return result


def emit_validation_result(result: StartupValidationResult, *, logger_obj: logging.Logger | None = None) -> None:
    log = logger_obj or logger
    if not result.ok:
        from utils.structured_log import log_event

        log_event(
            log,
            "runtime.startup.validation.failed",
            fatal=result.fatal,
            warnings=result.warnings,
        )
        raise RuntimeError(
            "Startup integrity validation failed:\n- " + "\n- ".join(result.fatal)
        )
    for w in result.warnings:
        log.warning("startup_integrity_warning: %s", w)
