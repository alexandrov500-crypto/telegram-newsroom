"""Offline operational analytics from metrics snapshots (v3.2 P2). Read-only."""

from __future__ import annotations

import gzip
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.ops_tooling import (
    OPS_SNAPSHOT_SCHEMA_VERSION,
    list_snapshots,
    load_snapshot,
)

ANALYTICS_SCHEMA_VERSION = 1
TREND_KEYS = (
    "publish_retries",
    "telethon_reconnects",
    "telethon_flood_waits",
    "publish_failures",
    "publish_lock_contention",
    "publishes",
    "drafts_published",
)


def default_reports_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "ops_reports"


def default_archive_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "ops_archive"


def parse_captured_at(iso: str) -> float | None:
    raw = (iso or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def load_snapshot_series_safe(
    history_dir: Path,
    *,
    limit: int = 500,
    max_age_sec: float | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load series; skip corrupt files; optional max age filter."""
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    now = time.time()
    files = list_snapshots(history_dir)[-limit:]
    for path in files:
        try:
            doc = load_snapshot(path)
        except ValueError:
            skipped.append(path.name)
            continue
        ts = parse_captured_at(str(doc.get("captured_at") or ""))
        if max_age_sec is not None and ts is not None and (now - ts) > max_age_sec:
            continue
        diag = doc.get("diagnostics") or {}
        rows.append(
            {
                "captured_at": doc.get("captured_at"),
                "ts": ts,
                "filename": path.name,
                "metrics": dict(diag.get("metrics") or {}),
                "retry_burst_window": int(diag.get("retry_burst_window") or 0),
                "status": str(diag.get("status") or ""),
                "findings_count": len(list(diag.get("findings") or [])),
            }
        )
    return rows, skipped


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return float(s[lo])
    frac = k - lo
    return float(s[lo] * (1 - frac) + s[hi] * frac)


def _counter_deltas(series: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    prev: int | None = None
    for row in series:
        cur = int((row.get("metrics") or {}).get(key, 0) or 0)
        if prev is not None:
            out.append(float(max(0, cur - prev)))
        prev = cur
    return out


def _values_over_time(series: list[dict[str, Any]], key: str) -> list[float]:
    return [float((r.get("metrics") or {}).get(key, 0) or 0) for r in series]


def detect_anomaly_windows(series: list[dict[str, Any]], *, key: str = "publish_retries") -> list[dict[str, Any]]:
    deltas = _counter_deltas(series, key)
    if len(deltas) < 3:
        return []
    mean = sum(deltas) / len(deltas)
    var = sum((x - mean) ** 2 for x in deltas) / len(deltas)
    std = math.sqrt(var)
    threshold = mean + max(2.0, 2 * std)
    windows: list[dict[str, Any]] = []
    for i, d in enumerate(deltas):
        if d >= threshold and d > 0:
            idx = i + 1
            if idx < len(series):
                windows.append(
                    {
                        "metric": key,
                        "delta": d,
                        "captured_at": series[idx].get("captured_at"),
                        "threshold": round(threshold, 4),
                    }
                )
    return windows[:24]


def rolling_means(values: list[float], window: int = 5) -> list[float]:
    if window < 1:
        window = 1
    out: list[float] = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1) : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def compute_publish_activity_proxy(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Inter-snapshot publish counter deltas (not wall-clock Telegram latency)."""
    deltas = _counter_deltas(series, "publishes")
    drafts = _counter_deltas(series, "drafts_published")
    combined = [a + b for a, b in zip(deltas, drafts)] if deltas and drafts and len(deltas) == len(drafts) else deltas or drafts or [0.0]
    return {
        "p50": round(_percentile(combined, 50), 4),
        "p95": round(_percentile(combined, 95), 4),
        "p99": round(_percentile(combined, 99), 4),
        "interpretation": "counter_delta_proxy_not_wall_clock_latency",
    }


def daily_summaries(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in series:
        raw = str(row.get("captured_at") or "")[:10]
        if not raw:
            continue
        buckets.setdefault(raw, []).append(row)
    summaries: list[dict[str, Any]] = []
    for day in sorted(buckets.keys()):
        rows = buckets[day]
        m: dict[str, int] = {}
        for key in TREND_KEYS:
            if not rows:
                m[key] = 0
                continue
            vals = [int((r.get("metrics") or {}).get(key, 0) or 0) for r in rows]
            m[key] = max(0, vals[-1] - vals[0]) if len(vals) >= 2 else 0
        summaries.append(
            {
                "day": day,
                "snapshot_count": len(rows),
                "metric_deltas": m,
                "max_retry_burst": max((int(r.get("retry_burst_window") or 0) for r in rows), default=0),
            }
        )
    return summaries


def build_analytics_summary(
    history_dir: Path,
    *,
    limit: int = 200,
    max_age_sec: float | None = None,
) -> dict[str, Any]:
    series, skipped = load_snapshot_series_safe(history_dir, limit=limit, max_age_sec=max_age_sec)
    trends: dict[str, Any] = {}
    for key in TREND_KEYS:
        deltas = _counter_deltas(series, key)
        levels = _values_over_time(series, key)
        trends[key] = {
            "delta_total": int(sum(deltas)) if deltas else 0,
            "max_level": int(max(levels)) if levels else 0,
            "rolling_mean_last": round(rolling_means(deltas)[-1], 4) if deltas else 0.0,
        }
    return {
        "schema_version": ANALYTICS_SCHEMA_VERSION,
        "analytics_kind": "ops_summary",
        "read_only": True,
        "offline": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot_count": len(series),
        "skipped_corrupt": skipped,
        "trends": trends,
        "anomaly_windows": detect_anomaly_windows(series, key="publish_retries")
        + detect_anomaly_windows(series, key="telethon_reconnects"),
        "publish_activity_proxy_percentiles": compute_publish_activity_proxy(series),
        "retry_burst": {
            "max": max((int(r.get("retry_burst_window") or 0) for r in series), default=0),
            "p95": round(_percentile([float(r.get("retry_burst_window") or 0) for r in series], 95), 4),
        },
        "daily_summaries": daily_summaries(series),
        "series": series,
    }


def analytics_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Operational analytics summary",
        "",
        f"Generated: {summary.get('generated_at')}",
        f"Snapshots analyzed: {summary.get('snapshot_count')}",
        f"Skipped corrupt: {len(summary.get('skipped_corrupt') or [])}",
        "",
        "## Trends (counter deltas)",
        "",
    ]
    for key, body in sorted((summary.get("trends") or {}).items()):
        lines.append(f"- **{key}**: delta={body.get('delta_total')} max_level={body.get('max_level')}")
    lines.extend(
        [
            "",
            "## Anomaly windows",
            "",
        ]
    )
    anomalies = summary.get("anomaly_windows") or []
    if not anomalies:
        lines.append("_None detected._")
    else:
        for a in anomalies[:12]:
            lines.append(f"- {a.get('metric')} delta={a.get('delta')} at {a.get('captured_at')}")
    proxy = summary.get("publish_activity_proxy_percentiles") or {}
    lines.extend(
        [
            "",
            "## Publish activity proxy (percentiles)",
            "",
            f"- p50={proxy.get('p50')} p95={proxy.get('p95')} p99={proxy.get('p99')}",
            f"- _{proxy.get('interpretation')}_",
            "",
        ]
    )
    return "\n".join(lines)


def svg_sparkline(
    values: list[float],
    *,
    title: str,
    width: int = 420,
    height: int = 90,
) -> str:
    if not values:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f'<text x="8" y="20">{title} (no data)</text></svg>'
        )
    pad = 8
    inner_w = width - 2 * pad
    inner_h = height - 2 * pad
    vmin = min(values)
    vmax = max(values)
    span = vmax - vmin or 1.0
    pts: list[str] = []
    n = len(values)
    for i, v in enumerate(values):
        x = pad + (inner_w * i / max(1, n - 1))
        y = pad + inner_h - ((v - vmin) / span) * inner_h
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img">'
        f'<title>{title}</title>'
        f'<rect width="100%" height="100%" fill="#fafafa"/>'
        f'<polyline fill="none" stroke="#2563eb" stroke-width="2" points="{poly}"/>'
        f'<text x="{pad}" y="{height - 2}" font-size="10" fill="#444">{title}</text>'
        f"</svg>"
    )


def build_visualization_bundle(summary: dict[str, Any]) -> dict[str, str]:
    series = summary.get("series") or []
    charts: dict[str, str] = {}
    mapping = {
        "publish_retries": "Retry amplification (level)",
        "telethon_reconnects": "Reconnect frequency (level)",
        "telethon_flood_waits": "FloodWait count (level)",
        "publish_lock_contention": "Lock contention (level)",
    }
    for key, title in mapping.items():
        charts[f"{key}.svg"] = svg_sparkline(_values_over_time(series, key), title=title)
    pub_delta = _counter_deltas(series, "publishes")
    charts["publish_activity_proxy.svg"] = svg_sparkline(pub_delta, title="Publish activity proxy (delta)")
    retry_burst = [float(r.get("retry_burst_window") or 0) for r in series]
    charts["retry_burst_window.svg"] = svg_sparkline(retry_burst, title="Retry burst window")
    return charts


def archive_snapshots(
    history_dir: Path,
    archive_dir: Path,
    *,
    older_than_days: int = 14,
    max_archive_bytes: int = 50 * 1024 * 1024,
) -> dict[str, Any]:
    archive_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - older_than_days * 86400
    archived = 0
    bytes_total = 0
    errors: list[str] = []
    for path in list(list_snapshots(history_dir)):
        try:
            doc = load_snapshot(path)
        except ValueError:
            continue
        ts = parse_captured_at(str(doc.get("captured_at") or ""))
        if ts is None or ts >= cutoff:
            continue
        month = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
        dest_dir = archive_dir / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{path.stem}.json.gz"
        raw = path.read_bytes()
        dest.write_bytes(gzip.compress(raw))
        if verify_archive_file(dest):
            path.unlink(missing_ok=True)
            archived += 1
            bytes_total += dest.stat().st_size
        else:
            errors.append(dest.name)
            dest.unlink(missing_ok=True)
        if bytes_total > max_archive_bytes:
            break
    return {
        "archived": archived,
        "archive_bytes": bytes_total,
        "errors": errors,
    }


def verify_archive_file(path: Path) -> bool:
    try:
        data = gzip.decompress(path.read_bytes())
        doc = json.loads(data.decode("utf-8"))
        return isinstance(doc, dict) and int(doc.get("schema_version", 0)) == OPS_SNAPSHOT_SCHEMA_VERSION
    except Exception:
        return False


def build_shift_handoff(
    history_dir: Path,
    *,
    hours: float = 24.0,
    reports_dir: Path | None = None,
) -> str:
    max_age = hours * 3600.0
    summary = build_analytics_summary(history_dir, limit=500, max_age_sec=max_age)
    lines = [
        "# Shift handoff report",
        "",
        f"Generated: {summary.get('generated_at')}",
        f"Window: last {hours}h",
        f"Snapshots: {summary.get('snapshot_count')}",
        "",
        "## Rollback readiness",
        "",
        "- Instant rollback: set `DRY_RUN=true` and restart services",
        "- See docs/runbooks/controlled_activation.md",
        "",
        "## Unresolved retries / failures",
        "",
    ]
    trends = summary.get("trends") or {}
    lines.append(f"- Publish retries (delta): {trends.get('publish_retries', {}).get('delta_total', 0)}")
    lines.append(f"- Publish failures (delta): {trends.get('publish_failures', {}).get('delta_total', 0)}")
    lines.append(f"- Max retry burst window: {(summary.get('retry_burst') or {}).get('max')}")
    lines.extend(["", "## Reconnect / FloodWait", ""])
    lines.append(f"- Reconnects delta: {trends.get('telethon_reconnects', {}).get('delta_total', 0)}")
    lines.append(f"- FloodWait delta: {trends.get('telethon_flood_waits', {}).get('delta_total', 0)}")
    lines.extend(["", "## Queue / lock observations", ""])
    lines.append(f"- Lock contention delta: {trends.get('publish_lock_contention', {}).get('delta_total', 0)}")
    lines.append("_For live queue depth run `tools/queue_introspection.py` at shift start._")
    lines.extend(["", "## Anomalies", ""])
    anomalies = summary.get("anomaly_windows") or []
    if not anomalies:
        lines.append("_None in window._")
    else:
        for a in anomalies[:8]:
            lines.append(f"- {a.get('metric')} +{a.get('delta')} @ {a.get('captured_at')}")
    lines.extend(["", "## Daily rollup", ""])
    for day in (summary.get("daily_summaries") or [])[-3:]:
        lines.append(f"- {day.get('day')}: snapshots={day.get('snapshot_count')} retries_delta={day.get('metric_deltas', {}).get('publish_retries')}")
    if reports_dir and reports_dir.is_dir():
        lines.extend(["", "## Reports", "", f"- Analytics dir: `{reports_dir}`"])
    lines.append("")
    return "\n".join(lines)
