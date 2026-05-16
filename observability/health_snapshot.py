"""Bounded latest-only runtime health snapshot (stdlib, no metrics backend)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION

HEALTH_SNAPSHOT_REL = Path("runtime") / "health_snapshot.json"
HEALTH_SNAPSHOT_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

# Stable top-level key order for deterministic JSON.
SNAPSHOT_KEY_ORDER: tuple[str, ...] = (
    "schema_version",
    "collected_articles",
    "clustered_articles",
    "failed_steps",
    "generated_at",
    "generated_drafts",
    "pipeline_status",
    "processed_sources",
    "published_posts",
    "qualification_status",
    "retention_bundle_size_mb",
    "runtime_duration_sec",
)


class HealthSnapshot(TypedDict):
    generated_at: str
    pipeline_status: str
    processed_sources: int
    collected_articles: int
    clustered_articles: int
    generated_drafts: int
    published_posts: int
    failed_steps: list[str]
    runtime_duration_sec: float
    retention_bundle_size_mb: float | None
    qualification_status: str | None


@dataclass(frozen=True)
class HealthSnapshotInputs:
    """Optional sidecars used when building a snapshot after nightly ops."""

    ops_report: dict[str, Any]
    output_dir: Path | None = None
    benchmark: dict[str, Any] | None = None
    qualification: dict[str, Any] | None = None
    runtime_duration_sec: float | None = None


def default_health_snapshot_path(base_dir: Path) -> Path:
    """``{base_dir}/runtime/health_snapshot.json`` (single latest file)."""
    return base_dir.expanduser().resolve() / HEALTH_SNAPSHOT_REL


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _duration_from_report(report: dict[str, Any], override_sec: float | None) -> float:
    if override_sec is not None and override_sec >= 0:
        return round(float(override_sec), 3)
    started = str(report.get("started_at") or "")
    completed = str(report.get("completed_at") or "")
    if not started or not completed:
        return 0.0
    try:
        from datetime import datetime

        fmt = "%Y-%m-%dT%H:%M:%SZ"
        t0 = datetime.strptime(started, fmt).timestamp()
        t1 = datetime.strptime(completed, fmt).timestamp()
        return round(max(0.0, t1 - t0), 3)
    except (TypeError, ValueError):
        return 0.0


def _metrics_from_benchmark(benchmark: dict[str, Any] | None) -> dict[str, int]:
    if not benchmark:
        return {
            "collected_articles": 0,
            "clustered_articles": 0,
            "generated_drafts": 0,
            "published_posts": 0,
            "processed_sources": 0,
        }
    exp = benchmark.get("metrics_export") or {}
    counters = dict(exp.get("counters") or {}) if isinstance(exp, dict) else {}
    posts = int(counters.get("posts_collected") or 0)
    clusters = int(counters.get("clusters_created") or 0)
    drafts = int(counters.get("drafts_generated") or 0)
    publishes = int(counters.get("publishes") or 0) + int(counters.get("drafts_published") or 0)
    sources = 0
    settings_block = benchmark.get("settings")
    if isinstance(settings_block, dict):
        ch = settings_block.get("source_channels")
        if isinstance(ch, (list, tuple)):
            sources = len(ch)
    return {
        "collected_articles": posts,
        "clustered_articles": clusters,
        "generated_drafts": drafts,
        "published_posts": publishes,
        "processed_sources": sources,
    }


def _bundle_size_mb(output_dir: Path | None) -> float | None:
    if output_dir is None:
        return None
    zp = output_dir / "runtime_bundle.zip"
    if not zp.is_file():
        return None
    return round(zp.stat().st_size / (1024 * 1024), 4)


def _qualification_status(
    qualification: dict[str, Any] | None, ops_report: dict[str, Any]
) -> str | None:
    if qualification is not None:
        st = qualification.get("qualification_status")
        return str(st) if st is not None else None
    for step in ops_report.get("steps") or []:
        if isinstance(step, dict) and step.get("name") == "qualification":
            st = step.get("status")
            if st == "SKIPPED":
                return None
            return str(st) if st is not None else None
    return None


def _failed_steps(ops_report: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for step in ops_report.get("steps") or []:
        if isinstance(step, dict) and str(step.get("status")) == "FAIL":
            name = str(step.get("name") or "")
            if name:
                out.append(name)
    return sorted(out)


def build_health_snapshot(
    *,
    ops_report: dict[str, Any],
    output_dir: Path | None = None,
    benchmark: dict[str, Any] | None = None,
    qualification: dict[str, Any] | None = None,
    runtime_duration_sec: float | None = None,
) -> dict[str, Any]:
    """Build a deterministic health snapshot dict from a nightly/ops report and optional sidecars."""
    metrics = _metrics_from_benchmark(benchmark)
    snap: dict[str, Any] = {
        "schema_version": HEALTH_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "pipeline_status": str(ops_report.get("status") or "UNKNOWN"),
        "processed_sources": int(metrics["processed_sources"]),
        "collected_articles": int(metrics["collected_articles"]),
        "clustered_articles": int(metrics["clustered_articles"]),
        "generated_drafts": int(metrics["generated_drafts"]),
        "published_posts": int(metrics["published_posts"]),
        "failed_steps": _failed_steps(ops_report),
        "runtime_duration_sec": _duration_from_report(ops_report, runtime_duration_sec),
        "retention_bundle_size_mb": _bundle_size_mb(output_dir),
        "qualification_status": _qualification_status(qualification, ops_report),
    }
    return {k: snap[k] for k in SNAPSHOT_KEY_ORDER}


def build_health_snapshot_from_inputs(inputs: HealthSnapshotInputs) -> dict[str, Any]:
    od = inputs.output_dir.expanduser().resolve() if inputs.output_dir else None
    bench = inputs.benchmark
    qual = inputs.qualification
    if od is not None:
        bp = od / "ops_benchmark.json"
        if bench is None and bp.is_file():
            bench = load_health_snapshot_sidecar_json(bp)
        qp = od / "qualification.json"
        if qual is None and qp.is_file():
            qual = load_health_snapshot_sidecar_json(qp)
    return build_health_snapshot(
        ops_report=inputs.ops_report,
        output_dir=od,
        benchmark=bench,
        qualification=qual,
        runtime_duration_sec=inputs.runtime_duration_sec,
    )


def load_health_snapshot_sidecar_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def write_health_snapshot(path: Path, snapshot: dict[str, Any]) -> Path:
    """Atomic replace write; only the latest snapshot is kept at ``path``."""
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: snapshot[k] for k in SNAPSHOT_KEY_ORDER if k in snapshot}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def load_health_snapshot(path: Path) -> dict[str, Any] | None:
    dest = path.expanduser().resolve()
    if not dest.is_file():
        return None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def resolve_health_snapshot_path(path: Path | None, *, output_dir: Path | None) -> Path | None:
    if path is not None:
        p = path.expanduser().resolve()
        if p.is_dir():
            return default_health_snapshot_path(p)
        return p
    if output_dir is not None:
        return default_health_snapshot_path(output_dir)
    return None


def render_health_summary(snapshot: dict[str, Any]) -> str:
    lines = [
        f"Pipeline status: {snapshot.get('pipeline_status', 'UNKNOWN')}",
        f"Collected articles: {snapshot.get('collected_articles', 0)}",
        f"Generated drafts: {snapshot.get('generated_drafts', 0)}",
        f"Published posts: {snapshot.get('published_posts', 0)}",
        f"Runtime duration: {snapshot.get('runtime_duration_sec', 0)} sec",
    ]
    qual = snapshot.get("qualification_status")
    if qual is not None:
        lines.append(f"Qualification status: {qual}")
    failed = snapshot.get("failed_steps") or []
    if failed:
        lines.append(f"Failed steps: {', '.join(failed)}")
    return "\n".join(lines) + "\n"
