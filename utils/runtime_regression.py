"""Lightweight baseline vs current comparison for runtime artifact bundles (zip)."""

from __future__ import annotations

import json
import math
import time
import zipfile
from pathlib import Path
from typing import Any, Literal

from utils.runtime_bundle import BUNDLE_DIR_NAME

MetricStatus = Literal["OK", "WARNING", "FAIL"]

# Operational metrics (fixed order for deterministic reports / JSON).
METRIC_ORDER: tuple[str, ...] = (
    "rss_mb",
    "peak_rss_mb",
    "avg_oldest_pending_age_sec_sampled_kinds",
    "queue_pressure_score",
    "pending_jobs_total",
    "event_history_bytes",
    "timeline_bytes",
    "suppression_bytes",
    "drift_bytes",
    "avg_moderation_publish_latency_sec",
    "avg_publish_attempts_recent",
    "reconnect_count",
    "recovery_count",
    "transport_failures",
)

METRIC_LABELS: dict[str, str] = {
    "rss_mb": "RSS memory",
    "peak_rss_mb": "RSS peak",
    "avg_oldest_pending_age_sec_sampled_kinds": "queue oldest age",
    "queue_pressure_score": "queue pressure",
    "pending_jobs_total": "pending jobs total",
    "event_history_bytes": "event_history size",
    "timeline_bytes": "timeline size",
    "suppression_bytes": "suppression state size",
    "drift_bytes": "drift snapshots size",
    "avg_moderation_publish_latency_sec": "moderation latency",
    "avg_publish_attempts_recent": "publish attempts (recent avg)",
    "reconnect_count": "telethon reconnects (counter)",
    "recovery_count": "transport op recoveries",
    "transport_failures": "transport / API failures (bounded proxy)",
}


def _safe_json_loads(raw: bytes) -> tuple[Any | None, str | None]:
    try:
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        return None, f"invalid_json:{type(exc).__name__}"


def load_runtime_bundle(zip_path: Path) -> tuple[dict[str, Any], list[str]]:
    """
    Load JSON members from ``runtime_bundle/*.json`` inside the zip.
    Returns (parsed_by_basename, warnings).
    """
    warnings: list[str] = []
    out: dict[str, Any] = {}
    zp = zip_path.expanduser().resolve()
    if not zp.is_file():
        warnings.append(f"bundle_not_found:{zp}")
        return out, warnings
    prefix = f"{BUNDLE_DIR_NAME}/"
    try:
        with zipfile.ZipFile(zp, "r") as zf:
            names = [n for n in zf.namelist() if n.startswith(prefix) and n.endswith(".json")]
            for name in sorted(names):
                base = name.split("/")[-1]
                try:
                    raw = zf.read(name)
                except OSError as exc:
                    warnings.append(f"zip_read_failed:{name}:{exc!r}")
                    continue
                data, err = _safe_json_loads(raw)
                if err:
                    warnings.append(f"{base}:{err}")
                    continue
                if isinstance(data, dict):
                    out[base] = data
                else:
                    warnings.append(f"{base}:expected_object")
    except zipfile.BadZipFile as exc:
        warnings.append(f"bad_zip:{exc!r}")
    return out, warnings


def _num(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _sum_queue_depths(depth: Any) -> float | None:
    if not isinstance(depth, dict):
        return None
    s = 0.0
    n = 0
    for _k, v in depth.items():
        if isinstance(v, dict) and "error" in v:
            continue
        fv = _num(v)
        if fv is not None:
            s += fv
            n += 1
    return s if n else None


def _max_pending_pressure(stability: dict[str, Any]) -> float | None:
    ts = stability.get("transport_sample") or {}
    if not isinstance(ts, dict):
        return None
    pb = ts.get("pressure_by_kind") or {}
    if not isinstance(pb, dict):
        return None
    mx = None
    for _kind, block in pb.items():
        if not isinstance(block, dict):
            continue
        p = _num(block.get("pending_depth"))
        if p is None:
            continue
        mx = p if mx is None else max(mx, p)
    return mx


def _queue_pressure_from_file(qp: dict[str, Any]) -> float | None:
    """Best-effort scalar from optional ``queue_pressure.json`` (CLI shapes vary)."""
    if not isinstance(qp, dict):
        return None
    if "pressure" in qp and isinstance(qp["pressure"], dict):
        p = qp["pressure"]
        v = _num(p.get("pending_depth"))
        if v is not None:
            return v
    mx = None
    for k, v in qp.items():
        if isinstance(v, dict) and "pressure" in v:
            pr = v.get("pressure")
            if isinstance(pr, dict):
                d = _num(pr.get("pending_depth"))
                if d is not None:
                    mx = d if mx is None else max(mx, d)
    return mx


def _recovery_count_from_stability(stability: dict[str, Any]) -> float | None:
    ts = stability.get("transport_sample") or {}
    if isinstance(ts, dict):
        pb = ts.get("pressure_by_kind")
        if isinstance(pb, dict):
            for _k, block in pb.items():
                if isinstance(block, dict):
                    rtm = block.get("redis_transport_metrics")
                    if isinstance(rtm, dict):
                        return _num(rtm.get("transport_op_recoveries"))
    return None


def extract_regression_metrics(loaded: dict[str, Any]) -> dict[str, float | None]:
    """
    Extract bounded scalars from bundle JSON dicts (keys = basename without path).
    Higher values = worse for all compared metrics in ``compare_runtime_metrics``.
    """
    stability = loaded.get("stability.json") or {}
    benchmark = loaded.get("benchmark.json") or {}
    summary = loaded.get("runtime_summary.json") or {}
    qp_file = loaded.get("queue_pressure.json") or {}

    src = stability if isinstance(stability, dict) and stability else benchmark
    if not isinstance(src, dict):
        src = {}

    rss_b = _num(src.get("rss_bytes"))
    rss_mb = rss_b / 1e6 if rss_b is not None else None

    bounded = ((summary.get("bounded_state_report") or {}) if isinstance(summary, dict) else {}) or {}
    peak_b = _num(bounded.get("rss_bytes"))
    peak_rss_mb = peak_b / 1e6 if peak_b is not None else None

    derived = (src.get("derived") or {}) if isinstance(src.get("derived"), dict) else {}
    oldest = _num(derived.get("avg_oldest_pending_age_sec_sampled_kinds"))

    qd = src.get("queue_depth_by_kind")
    pending_total = _sum_queue_depths(qd)

    qp_score = _max_pending_pressure(src if isinstance(stability, dict) and stability else {})
    if qp_score is None and isinstance(qp_file, dict):
        qp_score = _queue_pressure_from_file(qp_file)

    rsfb = (src.get("runtime_state_file_bytes") or {}) if isinstance(src.get("runtime_state_file_bytes"), dict) else {}
    if not rsfb and isinstance(benchmark.get("runtime_state_file_bytes"), dict):
        rsfb = benchmark["runtime_state_file_bytes"]

    def _byte(key: str) -> float | None:
        return _num(rsfb.get(key))

    editorial = (src.get("editorial_analytics") or {}) if isinstance(src.get("editorial_analytics"), dict) else {}
    if not editorial and isinstance(benchmark.get("editorial_analytics"), dict):
        editorial = benchmark["editorial_analytics"]
    mod_lat = _num(editorial.get("moderation_latency_avg_sec"))
    mod_attempts = _num(editorial.get("avg_publish_attempts_ring"))

    counters = ((src.get("metrics_export") or {}).get("counters") or {}) if isinstance(src.get("metrics_export"), dict) else {}
    if not counters and isinstance(benchmark.get("metrics_export"), dict):
        counters = (benchmark["metrics_export"].get("counters") or {})

    reconnect = _num(counters.get("telethon_reconnects"))
    recovery = _recovery_count_from_stability(stability) if isinstance(stability, dict) else None
    if recovery is None and isinstance(qp_file, dict):
        p = qp_file.get("pressure") if isinstance(qp_file.get("pressure"), dict) else None
        if isinstance(p, dict):
            rtm = p.get("redis_transport_metrics")
            if isinstance(rtm, dict):
                recovery = _num(rtm.get("transport_op_recoveries"))
    transport_fail: float | None = None
    if isinstance(counters, dict):
        tf = float(counters.get("telegram_api_failures") or 0)
        tf += float(counters.get("openai_failures") or 0)
        tf += float(counters.get("publish_failures") or 0)
        transport_fail = float(tf)

    out: dict[str, float | None] = {
        "rss_mb": rss_mb,
        "peak_rss_mb": peak_rss_mb,
        "avg_oldest_pending_age_sec_sampled_kinds": oldest,
        "queue_pressure_score": qp_score,
        "pending_jobs_total": pending_total,
        "event_history_bytes": _byte("event_history.json"),
        "timeline_bytes": _byte("operational_timeline.json"),
        "suppression_bytes": _byte("suppression_state.json"),
        "drift_bytes": _byte("editorial_drift_snapshots.json"),
        "avg_moderation_publish_latency_sec": mod_lat,
        "avg_publish_attempts_recent": mod_attempts,
        "reconnect_count": reconnect,
        "recovery_count": recovery,
        "transport_failures": transport_fail,
    }
    return {k: out[k] for k in METRIC_ORDER}


def classify_regression(
    *,
    baseline: float | None,
    current: float | None,
    warn_pct: float,
    fail_pct: float,
    ignore_missing: bool,
) -> tuple[MetricStatus, float | None, list[str]]:
    """
    Compare **current vs baseline** where an **increase** is worse.
    Returns (status, pct_change_vs_baseline_or_None, row_warnings).
    """
    row_warns: list[str] = []
    if baseline is None and current is None:
        return "OK", None, row_warns
    if baseline is None:
        if ignore_missing:
            return "OK", None, row_warns
        row_warns.append("baseline_missing")
        return "WARNING", None, row_warns
    if current is None:
        if ignore_missing:
            return "OK", None, row_warns
        row_warns.append("current_missing")
        return "WARNING", None, row_warns

    b = float(baseline)
    c = float(current)
    if b == 0.0:
        pct = 100.0 if c > 0 else 0.0
    else:
        pct = (c - b) / abs(b) * 100.0

    if pct <= 0:
        return "OK", round(pct, 4), row_warns
    if pct >= fail_pct:
        return "FAIL", round(pct, 4), row_warns
    if pct >= warn_pct:
        return "WARNING", round(pct, 4), row_warns
    return "OK", round(pct, 4), row_warns


def compare_runtime_metrics(
    current: dict[str, float | None],
    baseline: dict[str, float | None],
    *,
    warn_pct: float,
    fail_pct: float,
    ignore_missing: bool,
    regression_skip_metrics: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], MetricStatus]:
    """
    Row dict keys: metric, baseline, current, pct_change, status, notes (list).
    Overall: FAIL if any FAIL else WARNING if any WARNING else OK.
    """
    rows: list[dict[str, Any]] = []
    glob_warns: list[str] = []
    worst: MetricStatus = "OK"
    rank = {"OK": 0, "WARNING": 1, "FAIL": 2}
    skip = regression_skip_metrics or frozenset()

    for key in METRIC_ORDER:
        if key in skip:
            rows.append(
                {
                    "baseline": baseline.get(key),
                    "current": current.get(key),
                    "metric": key,
                    "notes": ["regression_skipped:configured"],
                    "pct_change": None,
                    "status": "OK",
                },
            )
            continue
        b = baseline.get(key)
        c = current.get(key)
        st, pct, rw = classify_regression(
            baseline=b,
            current=c,
            warn_pct=warn_pct,
            fail_pct=fail_pct,
            ignore_missing=ignore_missing,
        )
        if rank[st] > rank[worst]:
            worst = st
        glob_warns.extend([f"{key}:{w}" for w in rw])
        rows.append(
            {
                "baseline": b,
                "current": c,
                "metric": key,
                "notes": rw,
                "pct_change": pct,
                "status": st,
            },
        )
    return rows, glob_warns, worst


def render_regression_report(
    rows: list[dict[str, Any]],
    overall: MetricStatus,
    *,
    baseline_label: str,
    current_label: str,
) -> str:
    lines = [
        "Runtime regression summary",
        "",
        f"baseline: {baseline_label}",
        f"current:  {current_label}",
        "",
    ]
    for row in rows:
        key = str(row.get("metric"))
        label = METRIC_LABELS.get(key, key)
        st = str(row.get("status"))
        pct = row.get("pct_change")
        if pct is None:
            lines.append(f"{label}: n/a {st}")
        else:
            sign = "+" if float(pct) > 0 else ""
            lines.append(f"{label}: {sign}{pct}% {st}")
    lines.extend(["", f"Overall status: {overall}"])
    return "\n".join(lines) + "\n"


def build_comparison_json(
    *,
    baseline_path: str,
    current_path: str,
    rows: list[dict[str, Any]],
    bundle_warnings: list[str],
    overall: MetricStatus,
    warn_pct: float,
    fail_pct: float,
    strict: bool,
    ignore_missing: bool,
    regression_skip_metrics: frozenset[str] | None = None,
) -> dict[str, Any]:
    skip_metrics = regression_skip_metrics or frozenset()
    return {
        "baseline_bundle": baseline_path,
        "compared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "current_bundle": current_path,
        "metrics": rows,
        "overall_status": overall,
        "threshold_config": {
            "fail_threshold_pct": fail_pct,
            "ignore_missing": ignore_missing,
            "regression_skip_metrics": sorted(skip_metrics) if skip_metrics else [],
            "strict": strict,
            "warning_threshold_pct": warn_pct,
        },
        "warnings": sorted(set(bundle_warnings)),
    }


def compute_exit_code(overall: MetricStatus, bundle_warnings: list[str], *, strict: bool) -> int:
    if overall == "FAIL":
        return 1
    if strict and (overall != "OK" or bundle_warnings):
        return 1
    return 0


def run_regression_comparison(
    baseline_zip: Path,
    current_zip: Path,
    *,
    warn_pct: float = 15.0,
    fail_pct: float = 50.0,
    strict: bool = False,
    ignore_missing: bool = False,
    regression_skip_metrics: frozenset[str] | None = None,
) -> tuple[dict[str, Any], int]:
    b_load, b_warn = load_runtime_bundle(baseline_zip)
    c_load, c_warn = load_runtime_bundle(current_zip)
    pref_b = [f"baseline:{w}" for w in b_warn]
    pref_c = [f"current:{w}" for w in c_warn]
    bm = extract_regression_metrics(b_load)
    cm = extract_regression_metrics(c_load)
    rows, rw, overall = compare_runtime_metrics(
        cm,
        bm,
        warn_pct=warn_pct,
        fail_pct=fail_pct,
        ignore_missing=ignore_missing,
        regression_skip_metrics=regression_skip_metrics,
    )
    bundle_warnings = sorted(set(pref_b + pref_c + rw))
    payload = build_comparison_json(
        baseline_path=str(baseline_zip.resolve()),
        current_path=str(current_zip.resolve()),
        rows=rows,
        bundle_warnings=bundle_warnings,
        overall=overall,
        warn_pct=warn_pct,
        fail_pct=fail_pct,
        strict=strict,
        ignore_missing=ignore_missing,
        regression_skip_metrics=regression_skip_metrics,
    )
    code = compute_exit_code(overall, list(b_warn) + list(c_warn) + rw, strict=strict)
    return payload, code
