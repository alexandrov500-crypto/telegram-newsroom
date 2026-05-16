#!/usr/bin/env python3
"""Read-only live Telegram operational diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


_COUNTER_KEYS = (
    "telethon_reconnects",
    "telethon_flood_waits",
    "telegram_api_failures",
    "publish_retries",
    "publish_failures",
    "publishes",
    "drafts_published",
    "publish_lock_contention",
    "publish_lock_strict_denied",
    "publish_lock_redis_fallback",
    "publish_lock_stale_suspected",
    "cadence_blocked_publish",
    "worker_retry_safe_reorders",
    "openai_retries",
)


def collect_telegram_metrics() -> dict[str, int]:
    from utils.metrics import export_snapshot

    c = dict(export_snapshot().get("counters") or {})
    return {k: int(c.get(k) or 0) for k in _COUNTER_KEYS}


def _publish_outcomes(metrics: dict[str, int]) -> dict[str, int]:
    ok = metrics["publishes"] + metrics["drafts_published"]
    fail = metrics["publish_failures"]
    blocked = metrics["cadence_blocked_publish"]
    return {
        "success_total": ok,
        "failures": fail,
        "cadence_blocked": blocked,
        "retries": metrics["publish_retries"],
    }


def _session_instability(metrics: dict[str, int]) -> dict[str, Any]:
    reconnects = metrics["telethon_reconnects"]
    api_fail = metrics["telegram_api_failures"]
    flood = metrics["telethon_flood_waits"]
    reset_suspected = reconnects >= 5 and api_fail >= 3
    return {
        "reconnect_count": reconnects,
        "api_failure_count": api_fail,
        "flood_wait_count": flood,
        "session_reset_suspected": reset_suspected,
    }


def _reliability_buffers() -> dict[str, Any]:
    try:
        from utils.reliability_diagnostics import lock_events_snapshot, retry_traces_snapshot

        lock_ev = lock_events_snapshot()
        traces = retry_traces_snapshot()
        return {
            "lock_events_sampled": len(lock_ev),
            "retry_traces_sampled": len(traces),
            "recent_lock_events": lock_ev[-5:],
            "recent_retry_traces": traces[-5:],
        }
    except Exception:
        return {"lock_events_sampled": 0, "retry_traces_sampled": 0}


def collect_telegram_metrics_extended() -> dict[str, Any]:
    metrics = collect_telegram_metrics()
    return {
        "counters": metrics,
        "publish_outcomes": _publish_outcomes(metrics),
        "session_stability": _session_instability(metrics),
        "flood_wait_aggregation": {
            "telethon_flood_waits": metrics["telethon_flood_waits"],
            "note": "Collector FloodWait events; publisher uses rate limiter proactively",
        },
        "lock_contention": {
            "contention": metrics["publish_lock_contention"],
            "strict_denied": metrics["publish_lock_strict_denied"],
            "redis_fallback": metrics["publish_lock_redis_fallback"],
            "stale_suspected": metrics["publish_lock_stale_suspected"],
        },
        "retry_amplification": {
            "publish_retries": metrics["publish_retries"],
            "openai_retries": metrics["openai_retries"],
            "worker_safe_reorders": metrics["worker_retry_safe_reorders"],
        },
    }


def run_diagnostics() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    extended = collect_telegram_metrics_extended()
    metrics = extended["counters"]
    session = extended["session_stability"]

    storm_n = int(os.environ.get("RUNTIME_RETRY_STORM_COUNT", "40"))
    retry_burst = 0
    try:
        import asyncio
        from workers import state as worker_state

        async def _b() -> int:
            return int((await worker_state.collect_runtime_diag(type("S", (), {})())).get("retry_burst_window", 0))

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            retry_burst = asyncio.run(_b())
    except Exception:
        pass

    if metrics["telethon_reconnects"] > 10:
        findings.append(
            _hint(
                "MEDIUM",
                "reconnect_frequency",
                f"telethon_reconnects={metrics['telethon_reconnects']}",
                "Review session stability; see live_validation plan",
            )
        )
    if session.get("session_reset_suspected"):
        findings.append(
            _hint(
                "HIGH",
                "session_instability",
                f"reconnects={metrics['telethon_reconnects']} api_failures={metrics['telegram_api_failures']}",
                "Re-auth Telethon session; pause live validation",
            )
        )
    if metrics["telethon_flood_waits"] > 5:
        findings.append(
            _hint(
                "MEDIUM",
                "flood_wait_frequency",
                f"telethon_flood_waits={metrics['telethon_flood_waits']}",
                "Reduce publish cadence; review collector rate",
            )
        )
    if metrics["telegram_api_failures"] > 5:
        findings.append(
            _hint(
                "MEDIUM",
                "telegram_api_failures",
                f"telegram_api_failures={metrics['telegram_api_failures']}",
                "Check publish logs and rate limits",
            )
        )
    if retry_burst >= storm_n:
        findings.append(
            _hint(
                "HIGH",
                "retry_amplification",
                f"retry_burst_window={retry_burst} >= {storm_n}",
                "Stop live validation; fix upstream",
            )
        )
    if metrics["publish_retries"] > 15:
        findings.append(
            _hint(
                "MEDIUM",
                "publish_retry_amplification",
                f"publish_retries={metrics['publish_retries']}",
                "Inspect chunk failures; see retry_error_matrix.md",
            )
        )
    if metrics["publish_lock_contention"] > 20:
        findings.append(
            _hint(
                "LOW",
                "duplicate_publish_risk",
                "Elevated publish_lock_contention",
                "Verify PUBLISH_LOCK_STRICT with multi-worker",
            )
        )
    if metrics["publish_failures"] > 0 and metrics["publishes"] == 0 and metrics["drafts_published"] == 0:
        findings.append(
            _hint(
                "MEDIUM",
                "publish_failure_without_success",
                f"publish_failures={metrics['publish_failures']}",
                "Review DLQ and failed drafts before retrying publish",
            )
        )

    if _env_on("REDIS_ENABLED") and not _env_on("PUBLISH_LOCK_STRICT"):
        findings.append(
            _hint(
                "HIGH",
                "unsafe_live_config",
                "Redis without PUBLISH_LOCK_STRICT",
                "Enable strict lock before live multi-worker",
            )
        )

    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    worst = max((order.get(f["severity"], 0) for f in findings), default=0)
    status = "FAIL" if worst >= 3 else ("WARNING" if findings else "OK")

    dup_hint = metrics["publish_lock_contention"] > 0 or metrics["publish_lock_stale_suspected"] > 0

    return {
        "schema_version": 2,
        "read_only": True,
        "no_telegram_api_calls": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "metrics": metrics,
        "operational": extended,
        "retry_burst_window": retry_burst,
        "duplicate_publish_hints": dup_hint,
        "reliability_buffers": _reliability_buffers(),
        "live_validation_mode": _env_on("TELEGRAM_LIVE_VALIDATE"),
        "findings": findings,
        "notes": [
            "FloodWait: telethon_flood_waits counter + collector logs",
            "Publish latency: publish.telegram_chunks_duration_sec in structured logs",
            "Semantics: docs/operations/retry_error_matrix.md",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    report = run_diagnostics()
    if args.strict and report.get("findings"):
        highs = [f for f in report["findings"] if f.get("severity") == "HIGH"]
        if highs:
            report["status"] = "FAIL"
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
