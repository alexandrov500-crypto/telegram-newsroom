"""Centralized lightweight runtime warning list (no external APM)."""

from __future__ import annotations

from typing import Any


def collect_runtime_warnings(
    settings: Any,
    *,
    runtime_health: dict[str, Any] | None = None,
    metrics_export: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Deterministic heuristics over already-collected snapshots.
    Returns JSON-serializable dicts: code, severity, message, hints.
    """
    warns: list[dict[str, Any]] = []
    ctr = dict((metrics_export or {}).get("counters") or {})
    gauges = dict((metrics_export or {}).get("gauges") or {})

    of = int(ctr.get("openai_failures", 0) or 0)
    if of >= 3:
        warns.append(
            {
                "code": "openai_failures_elevated",
                "severity": "warn",
                "message": f"openai_failures counter is {of}",
                "hints": ["check model availability", "inspect logs openai.summarize_failed"],
            }
        )

    if int(ctr.get("cadence_blocked_publish", 0) or 0) >= 2:
        warns.append(
            {
                "code": "cadence_blocks_observed",
                "severity": "info",
                "message": "cadence_blocked_publish > 0 — quiet hours or burst pacing may be active",
                "hints": ["see docs/PUBLISHING_INTELLIGENCE.md", "review publish_cadence.json"],
            }
        )

    if int(ctr.get("skipped_intelligence_suppress", 0) or 0) >= 10:
        warns.append(
            {
                "code": "cluster_suppression_high",
                "severity": "info",
                "message": "many clusters suppressed by pipeline intelligence",
                "hints": [
                    "review editorial_policies.json thresholds",
                    "inspect draft_extras.pipeline_decision",
                ],
            }
        )

    dup_streak = int(ctr.get("skipped_duplicates", 0) or 0)
    if dup_streak >= 15:
        warns.append(
            {
                "code": "duplicate_skips_elevated",
                "severity": "warn",
                "message": "skipped_duplicates counter is high",
                "hints": [
                    "review DRAFT_SIMILARITY_THRESHOLD",
                    "inspect suppression duplicate_burst",
                ],
            }
        )

    rh = runtime_health or {}
    if rh and not rh.get("ok"):
        warns.append(
            {
                "code": "readiness_not_ok",
                "severity": "error",
                "message": "gather_runtime_health returned ok=false",
                "hints": ["curl /ready", "check database/redis sections"],
            }
        )

    q = ((rh.get("checks") or {}).get("queues") or {}) if rh else {}
    depths = dict(q.get("depth_by_kind") or {})
    warn_depth = int(getattr(settings, "runtime_queue_pending_warn", 500) or 500)
    for kind, depth in depths.items():
        if int(depth or 0) >= warn_depth:
            warns.append(
                {
                    "code": "queue_pending_depth_high",
                    "severity": "warn",
                    "message": f"queue {kind} pending depth {depth} >= {warn_depth}",
                    "hints": ["tools.admin_cli queue-pressure", "scale workers if sustained"],
                }
            )

    rtm = ((rh.get("checks") or {}).get("redis_transport_metrics") or {}) if rh else {}
    if isinstance(rtm, dict) and rtm.get("reconnects_total") is not None:
        try:
            if int(rtm.get("reconnects_total") or 0) >= 5:
                warns.append(
                    {
                        "code": "redis_transport_reconnects",
                        "severity": "warn",
                        "message": "redis transport reconnect counter elevated",
                        "hints": ["inspect Redis stability", "see redis_transport_metrics"],
                    }
                )
        except (TypeError, ValueError):
            pass

    if gauges:
        lat = gauges.get("ai_last_cluster_latency_sec")
        if lat is not None and float(lat) > 120.0:
            warns.append(
                {
                    "code": "ai_cluster_latency_high",
                    "severity": "info",
                    "message": f"last cluster AI latency gauge {lat}s",
                    "hints": ["check model slowness", "token volume in draft_extras.ai_generation"],
                }
            )

    return warns
