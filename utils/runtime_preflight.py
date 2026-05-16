"""Lightweight startup / preflight diagnostics (read-only, bounded, no daemon)."""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.engine.url import make_url

from utils.database_url import alembic_sync_url_from_async, is_sqlite_async_url, normalize_async_database_url
from utils.runtime_integrity import validate_event_history, validate_operational_timeline, validate_suppression_state

PreflightStatus = Literal["OK", "WARNING", "FAIL", "SKIPPED"]

CHECK_ORDER: tuple[str, ...] = (
    "filesystem",
    "settings",
    "sqlite",
    "runtime_state",
    "disk",
    "redis",
    "artifacts",
)

DISPLAY_LABELS: dict[str, str] = {
    "artifacts": "Artifacts layout",
    "disk": "Disk space",
    "filesystem": "Filesystem",
    "redis": "Redis",
    "runtime_state": "Runtime state",
    "settings": "Settings",
    "sqlite": "SQLite",
}


def _rank(st: str) -> int:
    return {"FAIL": 3, "WARNING": 2, "OK": 1, "SKIPPED": 0}.get(st, 0)


def _worst(a: PreflightStatus, b: PreflightStatus) -> PreflightStatus:
    ra, rb = _rank(a), _rank(b)
    return a if ra >= rb else b


def _writable_dir(path: Path) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    if not path.exists():
        msgs.append(f"missing:{path}")
        return False, msgs
    if not path.is_dir():
        msgs.append(f"not_directory:{path}")
        return False, msgs
    if not os.access(path, os.W_OK):
        msgs.append(f"not_writable:{path}")
        return False, msgs
    try:
        with tempfile.NamedTemporaryFile(prefix="preflight_", dir=str(path), delete=True) as tf:
            tf.write(b"ok")
            tf.flush()
    except OSError as exc:
        msgs.append(f"tempfile_failed:{path}:{exc!r}")
        return False, msgs
    return True, msgs


def run_filesystem_checks(
    *,
    runtime_dir: Path | None,
    artifacts_dir: Path | None,
    reports_dir: Path | None,
) -> dict[str, Any]:
    """Verify optional roots exist and accept a bounded temp file."""
    detail: dict[str, Any] = {}
    msgs: list[str] = []
    worst: PreflightStatus = "OK"
    for label, p in (
        ("artifacts_dir", artifacts_dir),
        ("reports_dir", reports_dir),
        ("runtime_dir", runtime_dir),
    ):
        if p is None:
            detail[label] = {"status": "skipped_not_specified"}
            continue
        rp = p.expanduser()
        try:
            rp = rp.resolve(strict=False)
        except OSError as exc:
            worst = _worst(worst, "FAIL")
            msgs.append(f"{label}:resolve_failed:{exc!r}")
            detail[label] = {"path": str(p), "ok": False}
            continue
        ok, m = _writable_dir(rp)
        msgs.extend(f"{label}:{x}" for x in m)
        if not ok:
            worst = _worst(worst, "FAIL")
        detail[label] = {"ok": ok, "path": str(rp)}
    if all(x is None for x in (runtime_dir, artifacts_dir, reports_dir)):
        msgs.append("filesystem:no_directories_specified")
        worst = _worst(worst, "WARNING")
    return {"detail": {k: detail[k] for k in sorted(detail)}, "messages": sorted(msgs), "status": worst}


def run_settings_checks(settings: Any | None, *, load_error: str | None = None) -> dict[str, Any]:
    if load_error:
        return {
            "detail": {"error": load_error},
            "messages": [f"settings_load_failed:{load_error}"],
            "status": "FAIL",
        }
    if settings is None:
        return {"detail": {}, "messages": ["settings:none"], "status": "FAIL"}
    msgs: list[str] = []
    worst: PreflightStatus = "OK"
    for attr in sorted(("database_url", "openai_api_key", "bot_token", "runtime_state_dir")):
        v = getattr(settings, attr, None)
        if v is None or (isinstance(v, str) and not v.strip()):
            msgs.append(f"settings:empty:{attr}")
            worst = "WARNING"
    return {
        "detail": {"deployment_profile": getattr(settings, "deployment_profile", None)},
        "messages": sorted(msgs),
        "status": worst,
    }


def run_sqlite_checks(settings: Any | None) -> dict[str, Any]:
    if settings is None:
        return {"detail": {}, "messages": ["sqlite:skipped_no_settings"], "status": "SKIPPED"}
    raw = str(getattr(settings, "database_url", "") or "")
    if not raw.strip():
        return {"detail": {}, "messages": ["sqlite:empty_database_url"], "status": "FAIL"}
    norm = normalize_async_database_url(raw)
    if not is_sqlite_async_url(norm):
        return {
            "detail": {"backend": "non_sqlite"},
            "messages": ["sqlite:preflight_skipped_non_sqlite_backend"],
            "status": "WARNING",
        }
    sync_url = alembic_sync_url_from_async(norm)
    try:
        u = make_url(sync_url)
    except Exception as exc:
        return {"detail": {}, "messages": [f"sqlite:url_parse:{exc!r}"], "status": "FAIL"}
    try:
        conn = sqlite3.connect(u.database or ":memory:", timeout=2.0)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return {"detail": {"url_hint": str(u.database or ":memory:")}, "messages": [f"sqlite:open_failed:{exc!r}"], "status": "FAIL"}
    return {"detail": {"path": str(u.database or ":memory:")}, "messages": [], "status": "OK"}


def run_runtime_state_checks(runtime_dir: Path | None) -> dict[str, Any]:
    if runtime_dir is None:
        return {"detail": {}, "messages": ["runtime_state:dir_unspecified"], "status": "WARNING"}
    rd = runtime_dir.expanduser()
    try:
        rd = rd.resolve(strict=False)
    except OSError as exc:
        return {"detail": {}, "messages": [f"runtime_state:resolve:{exc!r}"], "status": "FAIL"}
    if not rd.is_dir():
        return {"detail": {}, "messages": [f"runtime_state:not_a_directory:{rd}"], "status": "FAIL"}
    issues: list[str] = []
    issues.extend(validate_operational_timeline(str(rd)))
    issues.extend(validate_suppression_state(str(rd)))
    issues.extend(validate_event_history(str(rd)))
    fail = any("invalid_json" in x for x in issues)
    worst: PreflightStatus = "FAIL" if fail else ("WARNING" if issues else "OK")
    return {
        "detail": {"issues": sorted(issues)[:64]},
        "messages": sorted(issues)[:64],
        "status": worst,
    }


def run_disk_checks(
    *,
    anchor: Path | None,
    enabled: bool,
    min_free_mb: float,
) -> dict[str, Any]:
    if not enabled:
        return {"detail": {"reason": "check_disabled"}, "messages": [], "status": "SKIPPED"}
    if anchor is None:
        return {"detail": {}, "messages": ["disk:no_anchor_path"], "status": "WARNING"}
    p = anchor.expanduser()
    try:
        p = p.resolve(strict=False)
    except OSError as exc:
        return {"detail": {}, "messages": [f"disk:resolve:{exc!r}"], "status": "FAIL"}
    try:
        usage = shutil.disk_usage(str(p if p.is_dir() else p.parent))
    except OSError as exc:
        return {"detail": {}, "messages": [f"disk:usage_failed:{exc!r}"], "status": "FAIL"}
    free_mb = float(usage.free) / (1024.0 * 1024.0)
    ok = free_mb >= float(min_free_mb)
    st: PreflightStatus = "OK" if ok else "FAIL"
    return {
        "detail": {"free_mb": round(free_mb, 4), "min_free_mb": float(min_free_mb)},
        "messages": [] if ok else [f"disk:low_free_space free_mb={free_mb:.2f} min={min_free_mb}"],
        "status": st,
    }


def run_redis_checks(
    settings: Any | None,
    *,
    check_redis: bool,
    connect_timeout_sec: float = 1.0,
) -> dict[str, Any]:
    if not check_redis:
        return {"detail": {"reason": "check_disabled"}, "messages": [], "status": "SKIPPED"}
    if settings is None:
        return {"detail": {}, "messages": ["redis:skipped_no_settings"], "status": "SKIPPED"}
    if not bool(getattr(settings, "redis_enabled", False)):
        return {"detail": {}, "messages": ["redis:disabled_in_settings"], "status": "SKIPPED"}
    url = str(getattr(settings, "redis_url", "") or "").strip()
    if not url:
        return {"detail": {}, "messages": ["redis:empty_url"], "status": "WARNING"}
    try:
        import redis as redis_sync

        client = redis_sync.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=float(connect_timeout_sec),
            socket_timeout=float(connect_timeout_sec),
        )
        try:
            client.ping()
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as exc:
        return {"detail": {}, "messages": [f"redis:ping_failed:{exc!r}"], "status": "FAIL"}
    return {"detail": {"host_hint": url.split("@")[-1][:80]}, "messages": [], "status": "OK"}


def run_artifacts_layout_checks(
    *,
    artifacts_dir: Path | None,
    reports_dir: Path | None,
) -> dict[str, Any]:
    """Optional dirs: if provided but missing → WARNING."""
    msgs: list[str] = []
    worst: PreflightStatus = "OK"
    detail: dict[str, Any] = {}
    for label, p in (("artifacts_dir", artifacts_dir), ("reports_dir", reports_dir)):
        if p is None:
            detail[label] = {"present": None, "status": "skipped_not_specified"}
            continue
        rp = p.expanduser()
        try:
            rp = rp.resolve(strict=False)
        except OSError as exc:
            worst = _worst(worst, "WARNING")
            msgs.append(f"{label}:resolve_failed:{exc!r}")
            detail[label] = {"present": False}
            continue
        if rp.is_dir():
            detail[label] = {"path": str(rp), "present": True}
        else:
            worst = _worst(worst, "WARNING")
            msgs.append(f"{label}:missing_directory:{rp}")
            detail[label] = {"path": str(rp), "present": False}
    return {"detail": {k: detail[k] for k in sorted(detail)}, "messages": sorted(msgs), "status": worst}


def evaluate_preflight(
    *,
    runtime_dir: Path | None,
    artifacts_dir: Path | None,
    reports_dir: Path | None,
    settings: Any | None,
    settings_load_error: str | None,
    check_redis: bool,
    check_disk_space: bool,
    min_free_mb: float,
) -> dict[str, Any]:
    """Run all checks and assemble a JSON-serializable report."""
    rd = runtime_dir
    if rd is None and settings is not None:
        try:
            rd = Path(str(getattr(settings, "runtime_state_dir", ""))).expanduser()
        except Exception:
            rd = None

    checks: dict[str, dict[str, Any]] = {}
    checks["filesystem"] = run_filesystem_checks(
        runtime_dir=runtime_dir,
        artifacts_dir=artifacts_dir,
        reports_dir=reports_dir,
    )
    checks["settings"] = run_settings_checks(settings, load_error=settings_load_error)
    checks["sqlite"] = run_sqlite_checks(settings)
    checks["runtime_state"] = run_runtime_state_checks(rd)
    checks["disk"] = run_disk_checks(anchor=rd, enabled=check_disk_space, min_free_mb=min_free_mb)
    checks["redis"] = run_redis_checks(settings, check_redis=check_redis)
    checks["artifacts"] = run_artifacts_layout_checks(artifacts_dir=artifacts_dir, reports_dir=reports_dir)

    flat_warnings: list[str] = []
    for name in CHECK_ORDER:
        block = checks.get(name) or {}
        flat_warnings.extend(str(x) for x in (block.get("messages") or []))

    overall: PreflightStatus = "OK"
    for name in CHECK_ORDER:
        st = str((checks.get(name) or {}).get("status") or "OK")
        if st == "FAIL":
            overall = "FAIL"
            break
        if st == "WARNING":
            overall = "WARNING"

    preflight_ok = overall != "FAIL"

    return {
        "checks": {k: checks[k] for k in CHECK_ORDER},
        "flat_messages": sorted(set(flat_warnings)),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": overall,
        "preflight_ok": bool(preflight_ok),
    }


def render_status_line(label: str, status: str) -> str:
    st = str(status or "UNKNOWN").upper()
    if st == "SKIPPED":
        badge = "[SKIPPED]"
    elif st == "OK":
        badge = "[OK]"
    elif st == "WARNING":
        badge = "[WARNING]"
    elif st == "FAIL":
        badge = "[FAIL]"
    else:
        badge = f"[{st}]"
    return f"{badge} {label}"


def render_preflight_report(report: dict[str, Any]) -> str:
    chk = report.get("checks") or {}
    lines = ["Runtime preflight summary", ""]
    for key in CHECK_ORDER:
        label = DISPLAY_LABELS.get(key, key)
        st = str((chk.get(key) or {}).get("status") or "UNKNOWN")
        lines.append(render_status_line(label, st))
    lines.extend(
        [
            "",
            f"Overall: {report.get('overall_status')}",
            f"PREFLIGHT_OK: {str(bool(report.get('preflight_ok'))).lower()}",
        ],
    )
    msgs = report.get("flat_messages") or []
    if msgs:
        lines.extend(["", "Messages:"])
        lines.extend(f"  {m}" for m in msgs[:40])
    return "\n".join(lines) + "\n"


def strict_preflight_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    if not strict:
        return 0 if report.get("preflight_ok") else 1
    if str(report.get("overall_status")) != "OK":
        return 1
    return 0
