from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.runtime.profile import LoopMode, RuntimeCapabilities, RuntimeProfile


def loop_registration_manifest(
    caps: RuntimeCapabilities,
) -> list[tuple[str, LoopMode, float]]:
    """Loop name, mode, and expected heartbeat interval for the active runtime profile."""
    from bot.runtime.profile import RuntimeProfile

    entries: list[tuple[str, LoopMode, float]] = []
    if caps.profile == RuntimeProfile.MINIMAL_PILOT:
        entries.append(("pilot-ops", "active", float(caps.ops_loop_interval_sec)))
    else:
        entries.append(
            (
                "operations-platform",
                caps.operations_platform,
                float(caps.ops_loop_interval_sec),
            ),
        )

    entries.extend(
        [
            ("epistemic-integrity", caps.epistemic_integrity, 150.0),
            ("federated-cognitive-mesh", caps.federated_cognitive_mesh, 120.0),
            ("cognitive-runtime", caps.cognitive_runtime, 90.0),
            ("operator-signal-hub", caps.operator_signal_hub, 120.0),
        ],
    )

    if caps.autonomous_runtime != "disabled":
        interval = (
            float(caps.passive_loop_interval_sec)
            if caps.autonomous_runtime == "passive"
            else 45.0
        )
        entries.append(("autonomous-runtime", caps.autonomous_runtime, interval))

    if caps.rss_ingestion:
        entries.append(("rss-ingestion", "active", 90.0))
    if caps.reliability_layer:
        entries.append(("reliability-probe", "active", 30.0))

    return entries


def runtime_loops_classification(
    caps: RuntimeCapabilities,
) -> dict[str, list[str]]:
    active: list[str] = []
    passive: list[str] = []
    disabled: list[str] = []
    for name, mode, _ in loop_registration_manifest(caps):
        if mode == "disabled":
            disabled.append(name)
        elif mode == "passive":
            passive.append(name)
        else:
            active.append(name)
    return {"active": active, "passive": passive, "disabled": disabled}


def loops_eligible_for_watchdog(caps: RuntimeCapabilities) -> frozenset[str]:
    return frozenset(
        name
        for name, mode, _ in loop_registration_manifest(caps)
        if mode != "disabled"
    )
