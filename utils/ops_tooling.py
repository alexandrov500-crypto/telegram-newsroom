"""Read-only operational tooling helpers (v3.2 P1). No Telegram/Redis writes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

OPS_SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_MAX_SNAPSHOT_FILES = 200
DEFAULT_MAX_TOTAL_BYTES = 20 * 1024 * 1024


def default_history_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "ops_history"


def collect_diagnostics_payload() -> dict[str, Any]:
    from tools.live_telegram_diagnostics import run_diagnostics

    diag = run_diagnostics()
    return {
        "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_kind": "ops_metrics",
        "read_only": True,
        "no_telegram_api_calls": True,
        "no_redis_mutations": True,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "diagnostics": diag,
    }


def validate_snapshot_document(data: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if int(data.get("schema_version", 0)) != OPS_SNAPSHOT_SCHEMA_VERSION:
        issues.append("schema_version_mismatch")
    if not data.get("read_only"):
        issues.append("not_read_only")
    diag = data.get("diagnostics")
    if not isinstance(diag, dict):
        issues.append("missing_diagnostics")
    return issues


def persist_snapshot(
    history_dir: Path,
    payload: dict[str, Any] | None = None,
    *,
    filename: str | None = None,
) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    body = payload if payload is not None else collect_diagnostics_payload()
    issues = validate_snapshot_document(body)
    if issues:
        raise ValueError(f"snapshot validation failed: {issues}")
    name = filename or f"ops_metrics_{body['captured_at'].replace(':', '')}.json"
    path = history_dir / name
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"corrupt snapshot: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"corrupt snapshot: {path}")
    issues = validate_snapshot_document(data)
    if issues:
        raise ValueError(f"invalid snapshot {path}: {issues}")
    return data


def list_snapshots(history_dir: Path) -> list[Path]:
    if not history_dir.is_dir():
        return []
    files = sorted(history_dir.glob("ops_metrics_*.json"))
    return files


def rotate_snapshots(
    history_dir: Path,
    *,
    max_files: int = DEFAULT_MAX_SNAPSHOT_FILES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> dict[str, int]:
    files = list_snapshots(history_dir)
    removed = 0
    while len(files) > max_files:
        victim = files.pop(0)
        victim.unlink(missing_ok=True)
        removed += 1
    total = sum(f.stat().st_size for f in files if f.is_file())
    while files and total > max_total_bytes:
        victim = files.pop(0)
        size = victim.stat().st_size if victim.is_file() else 0
        victim.unlink(missing_ok=True)
        total -= size
        removed += 1
    return {"removed": removed, "kept": len(files), "total_bytes": total}


def summarize_snapshots(history_dir: Path, *, limit: int = 48) -> dict[str, Any]:
    files = list_snapshots(history_dir)
    if not files:
        return {
            "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_count": 0,
            "counters": {},
        }
    selected = files[-limit:]
    series: dict[str, list[int]] = {}
    for path in selected:
        doc = load_snapshot(path)
        metrics = dict((doc.get("diagnostics") or {}).get("metrics") or {})
        for k, v in metrics.items():
            series.setdefault(str(k), []).append(int(v or 0))
    counters: dict[str, Any] = {}
    for key, vals in sorted(series.items()):
        counters[key] = {
            "first": vals[0] if vals else 0,
            "last": vals[-1] if vals else 0,
            "delta": (vals[-1] - vals[0]) if len(vals) >= 2 else 0,
            "max": max(vals) if vals else 0,
        }
    return {
        "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_count": len(selected),
        "oldest": selected[0].name if selected else None,
        "newest": selected[-1].name if selected else None,
        "counters": counters,
    }


def _metric_keys() -> tuple[str, ...]:
    from tools.live_telegram_diagnostics import _COUNTER_KEYS  # noqa: PLC2701

    return _COUNTER_KEYS


def load_snapshot_series(history_dir: Path, *, limit: int = 96) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in list_snapshots(history_dir)[-limit:]:
        doc = load_snapshot(path)
        diag = doc.get("diagnostics") or {}
        rows.append(
            {
                "captured_at": doc.get("captured_at"),
                "filename": path.name,
                "metrics": dict(diag.get("metrics") or {}),
                "retry_burst_window": int(diag.get("retry_burst_window") or 0),
                "status": str(diag.get("status") or ""),
            }
        )
    return rows


def load_timeline_events(runtime_dir: Path, *, limit: int = 120) -> list[dict[str, Any]]:
    from dashboard.timeline import load_timeline_tail

    return load_timeline_tail(str(runtime_dir), limit=limit)


def build_timeline_report(
    history_dir: Path,
    *,
    runtime_dir: Path | None = None,
    limit: int = 96,
) -> dict[str, Any]:
    series = load_snapshot_series(history_dir, limit=limit)
    events: list[dict[str, Any]] = []
    if runtime_dir is not None and runtime_dir.is_dir():
        events = load_timeline_events(runtime_dir, limit=limit)

    publish_kinds = frozenset(
        {
            "publication_ok",
            "publish_cadence_blocked",
        }
    )
    publish_events = [e for e in events if str(e.get("kind") or "") in publish_kinds or "publish" in str(e.get("kind") or "")]

    flood_delta = 0
    reconnect_delta = 0
    retry_delta = 0
    if len(series) >= 2:
        a, b = series[0]["metrics"], series[-1]["metrics"]
        flood_delta = int(b.get("telethon_flood_waits", 0)) - int(a.get("telethon_flood_waits", 0))
        reconnect_delta = int(b.get("telethon_reconnects", 0)) - int(a.get("telethon_reconnects", 0))
        retry_delta = int(b.get("publish_retries", 0)) - int(a.get("publish_retries", 0))

    return {
        "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
        "read_only": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot_series_count": len(series),
        "trend": {
            "telethon_flood_waits_delta": flood_delta,
            "telethon_reconnects_delta": reconnect_delta,
            "publish_retries_delta": retry_delta,
        },
        "retry_burst_max": max((int(r.get("retry_burst_window") or 0) for r in series), default=0),
        "publish_timeline_events": publish_events[:48],
        "snapshot_series": series,
    }


def timeline_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Publish timeline report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Snapshots: {report.get('snapshot_series_count')}",
        "",
        "## Metric trends (first → last snapshot)",
        "",
        f"- FloodWait delta: {report.get('trend', {}).get('telethon_flood_waits_delta')}",
        f"- Reconnect delta: {report.get('trend', {}).get('telethon_reconnects_delta')}",
        f"- Publish retry delta: {report.get('trend', {}).get('publish_retries_delta')}",
        f"- Max retry burst window: {report.get('retry_burst_max')}",
        "",
        "## Recent operational timeline events",
        "",
    ]
    evs = report.get("publish_timeline_events") or []
    if not evs:
        lines.append("_No publish-related timeline events in window._")
    else:
        for ev in evs[:24]:
            lines.append(f"- `{ev.get('kind')}` ts={ev.get('ts')}")
    lines.append("")
    return "\n".join(lines)
