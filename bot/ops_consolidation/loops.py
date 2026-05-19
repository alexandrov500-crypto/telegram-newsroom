from __future__ import annotations

from typing import Any


# Pilot-relevant loops (minimal_pilot profile + ops layers).
PILOT_BACKGROUND_LOOPS: list[dict[str, Any]] = [
    {"name": "burn-in-watchdog", "interval_sec": 30, "tier": "critical", "owner": "observability"},
    {"name": "metrics-refresh", "interval_sec": 15, "tier": "operational", "owner": "observability"},
    {"name": "stream-metrics", "interval_sec": 15, "tier": "debug", "owner": "distributed"},
    {"name": "forensics-runtime-snapshot", "interval_sec": 300, "tier": "forensic", "owner": "ops_forensics"},
    {"name": "ops-lifecycle-maintenance", "interval_sec": 21600, "tier": "operational", "owner": "ops_lifecycle"},
    {"name": "ops-resilience-evaluation", "interval_sec": 120, "tier": "critical", "owner": "ops_resilience"},
    {"name": "story-maintenance", "interval_sec": 3600, "tier": "debug", "owner": "cognitive"},
    {"name": "rss-ingestion", "interval_sec": 90, "tier": "operational", "owner": "ingestion"},
    {"name": "pilot-ops", "interval_sec": 180, "tier": "operational", "owner": "operations"},
]


def inventory_background_loops() -> dict[str, Any]:
    """Loop inventory with consolidation notes — does not stop loops."""
    try:
        from bot.runtime.profile import get_runtime_capabilities
        from bot.runtime.loop_manifest import loop_registration_manifest, runtime_loops_classification

        caps = get_runtime_capabilities()
        manifest = loop_registration_manifest(caps)
        classification = runtime_loops_classification(caps)
    except Exception:
        manifest = []
        classification = {"active": [], "passive": [], "disabled": []}

    registered = [
        {
            "name": name,
            "mode": mode,
            "heartbeat_sec": interval,
            "consolidation_note": _loop_note(name, mode),
        }
        for name, mode, interval in manifest
    ]

    pilot_names = {l["name"] for l in PILOT_BACKGROUND_LOOPS}
    merge = list(PILOT_BACKGROUND_LOOPS)
    for r in registered:
        if r["name"] not in pilot_names and r["mode"] != "disabled":
            merge.append(
                {
                    "name": r["name"],
                    "interval_sec": int(r["heartbeat_sec"]),
                    "tier": "debug" if r["mode"] == "passive" else "operational",
                    "owner": "runtime_manifest",
                    "mode": r["mode"],
                },
            )

    recommendations: list[str] = []
    active_count = len([l for l in merge if l.get("tier") != "debug"])
    if active_count > 8:
        recommendations.append(
            "Consider disabling stream-metrics and story-maintenance under minimal_pilot",
        )
    if len(classification.get("disabled", [])) < 4:
        recommendations.append(
            "Profile has many enabled loops — verify RUNTIME_PROFILE=minimal_pilot",
        )

    return {
        "loops": merge,
        "count": len(merge),
        "active_manifest": classification.get("active", []),
        "disabled_manifest": classification.get("disabled", []),
        "rationalization_recommendations": recommendations,
    }


def _loop_note(name: str, mode: str) -> str:
    if mode == "disabled":
        return "disabled — no scheduler cost"
    if mode == "passive":
        return "passive — heartbeat only under pilot"
    if name in ("federated-cognitive-mesh", "cognitive-runtime", "epistemic-integrity"):
        return "candidate to disable in stability phase"
    return "active"
