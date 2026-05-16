#!/usr/bin/env python3
"""Operational benchmark snapshot (queues, metrics, RSS, JSON runtime files) — not microbench."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


async def _queue_depths() -> dict[str, Any]:
    try:
        from worker.job_queue import JobKind, get_job_queue

        q = get_job_queue()
        return {k.value: await q.depth(k) for k in JobKind}
    except RuntimeError:
        return {"mode": "uninitialized"}
    except Exception as exc:
        return {"error": repr(exc)}


def _runtime_file_sizes(runtime_dir: str) -> dict[str, int]:
    from editorial.intelligence_store import (
        drift_snapshots_path,
        event_history_path,
        operational_timeline_path,
        suppression_state_path,
    )

    out: dict[str, int] = {}
    for name, fn in (
        ("operational_timeline.json", operational_timeline_path),
        ("suppression_state.json", suppression_state_path),
        ("editorial_drift_snapshots.json", drift_snapshots_path),
        ("event_history.json", event_history_path),
    ):
        p = fn(runtime_dir)
        try:
            out[name] = int(p.stat().st_size) if p.is_file() else 0
        except OSError:
            out[name] = -1
    return out


def build_benchmark_payload(settings: Any) -> dict[str, Any]:
    from utils.diagnostics import process_uptime_sec, rss_bytes_best_effort
    from utils.editorial_analytics import export_editorial_analytics
    from utils.metrics import export_snapshot

    exp = export_snapshot()
    counters = dict(exp.get("counters") or {})
    posts = int(counters.get("posts_collected") or 0)
    skipped_dup = int(counters.get("skipped_duplicates") or 0)
    skipped_intel = int(counters.get("skipped_intelligence_suppress") or 0)
    publishes = int(counters.get("publishes") or 0) + int(counters.get("drafts_published") or 0)
    pub_fails = int(counters.get("publish_failures") or 0)
    oai_retries = int(counters.get("openai_retries") or 0)
    pub_retries = int(counters.get("publish_retries") or 0)
    suppression_ratio = round((skipped_dup + skipped_intel) / max(1, posts), 6) if posts else 0.0
    retry_freq = round((oai_retries + pub_retries) / max(1, posts), 6) if posts else float(oai_retries + pub_retries)
    editorial = export_editorial_analytics(counters)

    return {
        "ts": __import__("time").time(),
        "uptime_sec": round(process_uptime_sec(), 3),
        "rss_bytes": rss_bytes_best_effort(),
        "metrics_export": exp,
        "editorial_analytics": editorial,
        "derived": {
            "suppression_ratio_vs_posts": suppression_ratio,
            "retry_frequency_vs_posts": retry_freq,
            "publish_success_proxy": round(publishes / max(1, publishes + pub_fails), 6),
            "ai_last_cluster_latency_sec": (exp.get("gauges") or {}).get("ai_last_cluster_latency_sec"),
            "pipeline_duration_avg_sec": exp.get("pipeline_duration_avg_sec"),
            "avg_moderation_publish_latency_sec": editorial.get("moderation_latency_avg_sec"),
            "avg_publish_attempts_recent": editorial.get("avg_publish_attempts_ring"),
        },
        "runtime_state_file_bytes": _runtime_file_sizes(settings.runtime_state_dir),
    }


async def _optional_transport_pressure(settings: Any) -> dict[str, Any]:
    """Short-lived Redis/transport init for queue lag samples (opt-in; closes resources)."""
    from utils.queue_diagnostics import collect_queue_pressure
    from utils.redis_client import close_redis, init_redis_from_settings
    from worker.job_queue import JobKind, close_job_queue, init_job_queue
    from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport

    await init_redis_from_settings(settings)
    await init_job_queue(settings)
    await init_reliable_transport(settings)
    try:
        transport = get_reliable_transport()
        out: dict[str, Any] = {}
        ages: list[float] = []
        for k in JobKind:
            pr = await collect_queue_pressure(transport, k, settings)
            out[k.value] = pr
            lag = pr.get("oldest_pending_age_sec")
            if lag is not None:
                ages.append(float(lag))
        derived_avg = round(sum(ages) / len(ages), 4) if ages else None
        return {"pressure_by_kind": out, "avg_oldest_pending_age_sec_sampled_kinds": derived_avg}
    finally:
        await close_reliable_transport()
        await close_job_queue()
        await close_redis()


async def async_main(settings: Any, *, sample_transport: bool) -> dict[str, Any]:
    payload = build_benchmark_payload(settings)
    payload["queue_depth_by_kind"] = await _queue_depths()
    if sample_transport:
        try:
            payload["transport_sample"] = await _optional_transport_pressure(settings)
        except Exception as exc:
            payload["transport_sample"] = {"ok": False, "error": repr(exc)}
        ts = payload.get("transport_sample")
        if isinstance(ts, dict) and ts.get("avg_oldest_pending_age_sec_sampled_kinds") is not None:
            payload["derived"]["avg_oldest_pending_age_sec_sampled_kinds"] = ts["avg_oldest_pending_age_sec_sampled_kinds"]
    return payload


def main() -> int:
    p = argparse.ArgumentParser(description="Operational runtime benchmark snapshot")
    p.add_argument(
        "--sample-transport",
        action="store_true",
        help="Briefly init Redis+reliable transport to sample per-kind queue pressure (closes after sample)",
    )
    p.add_argument("--json-out", default="", help="Write JSON report")
    p.add_argument("--html-out", default="", help="Write HTML report")
    args = p.parse_args()

    from app.config import load_settings
    from utils.evidence_reports import build_runtime_stability_report

    settings = load_settings()
    payload = asyncio.run(async_main(settings, sample_transport=bool(args.sample_transport)))
    txt = build_runtime_stability_report(payload, format="json")
    print(txt)
    if args.json_out:
        Path(args.json_out).write_text(txt, encoding="utf-8")
    if args.html_out:
        Path(args.html_out).write_text(build_runtime_stability_report(payload, format="html"), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
