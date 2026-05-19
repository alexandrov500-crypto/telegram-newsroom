from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Literal

LoopMode = Literal["active", "passive", "disabled"]


class RuntimeProfile(str, Enum):
    MINIMAL_PILOT = "minimal_pilot"
    STANDARD_LIVE = "standard_live"
    RESEARCH_FULL = "research_full"


@dataclass(frozen=True)
class RuntimeCapabilities:
    profile: RuntimeProfile

    telegram_operator: bool = True
    controlled_live: bool = True
    rss_ingestion: bool = True
    health_watchdog: bool = True
    production_safety: bool = True
    reliability_layer: bool = True

    research_stack: bool = False
    cognitive_runtime: LoopMode = "disabled"
    federated_cognitive_mesh: LoopMode = "disabled"
    epistemic_integrity: LoopMode = "disabled"
    operator_signal_hub: LoopMode = "disabled"
    autonomous_runtime: LoopMode = "passive"
    operations_platform: LoopMode = "disabled"

    live_ops_stack: bool = False
    ops_certification: bool = False
    rc1_stack: bool = False
    ga_ops: bool = False
    post_ga: bool = False
    ops_evolution: bool = False
    platform_stack: bool = False
    ops_playbook: bool = False
    live_deploy_stack: bool = False
    week1_stack: bool = False
    operational_memory: bool = False
    go_live_stack: bool = False

    digest_scheduler: bool = False
    analytics_scheduler: bool = False
    telegram_ingestion: bool = False
    story_maintenance: bool = False
    cluster_coordinator: bool = False
    openai_daily_aggregate: bool = False
    burnin_auto_start: bool = False

    ops_loop_interval_sec: int = 120
    passive_loop_interval_sec: int = 300
    max_background_tasks: int = 12


def resolve_runtime_profile(raw: str | None = None) -> RuntimeProfile:
    explicit = (raw or os.getenv("RUNTIME_PROFILE", "")).strip().lower()
    if explicit in ("minimal_pilot", "minimal", "pilot"):
        return RuntimeProfile.MINIMAL_PILOT
    if explicit in ("standard_live", "standard", "live"):
        return RuntimeProfile.STANDARD_LIVE
    if explicit in ("research_full", "research", "full"):
        return RuntimeProfile.RESEARCH_FULL
    if os.getenv("LIVE_MODE", "").strip().lower() == "canary":
        return RuntimeProfile.MINIMAL_PILOT
    if os.getenv("APP_ENV", "").strip().lower() == "pilot":
        return RuntimeProfile.MINIMAL_PILOT
    if os.getenv("CONTROLLED_LIVE_ENABLED", "").lower() in ("1", "true", "yes"):
        return RuntimeProfile.STANDARD_LIVE
    return RuntimeProfile.STANDARD_LIVE


def capabilities_for(profile: RuntimeProfile) -> RuntimeCapabilities:
    if profile == RuntimeProfile.MINIMAL_PILOT:
        return RuntimeCapabilities(
            profile=profile,
            research_stack=False,
            cognitive_runtime="disabled",
            federated_cognitive_mesh="disabled",
            epistemic_integrity="disabled",
            operator_signal_hub="disabled",
            autonomous_runtime="passive",
            operations_platform="disabled",
            live_ops_stack=False,
            ops_certification=False,
            rc1_stack=False,
            ga_ops=False,
            post_ga=False,
            ops_evolution=False,
            platform_stack=False,
            ops_playbook=False,
            live_deploy_stack=False,
            week1_stack=False,
            operational_memory=False,
            go_live_stack=False,
            digest_scheduler=False,
            analytics_scheduler=False,
            telegram_ingestion=False,
            story_maintenance=False,
            cluster_coordinator=False,
            openai_daily_aggregate=False,
            burnin_auto_start=False,
            ops_loop_interval_sec=int(os.getenv("MINIMAL_PILOT_OPS_INTERVAL_SEC", "120")),
            passive_loop_interval_sec=int(os.getenv("PASSIVE_LOOP_INTERVAL_SEC", "300")),
            max_background_tasks=10,
        )
    if profile == RuntimeProfile.RESEARCH_FULL:
        return RuntimeCapabilities(
            profile=profile,
            research_stack=True,
            cognitive_runtime="active",
            federated_cognitive_mesh="active",
            epistemic_integrity="active",
            operator_signal_hub="active",
            autonomous_runtime="active",
            operations_platform="active",
            live_ops_stack=True,
            ops_certification=True,
            rc1_stack=True,
            ga_ops=True,
            post_ga=True,
            ops_evolution=True,
            platform_stack=True,
            ops_playbook=True,
            live_deploy_stack=True,
            week1_stack=True,
            operational_memory=True,
            go_live_stack=True,
            digest_scheduler=True,
            analytics_scheduler=True,
            telegram_ingestion=True,
            story_maintenance=True,
            cluster_coordinator=True,
            openai_daily_aggregate=True,
            burnin_auto_start=True,
            ops_loop_interval_sec=180,
            passive_loop_interval_sec=120,
            max_background_tasks=32,
        )
    return RuntimeCapabilities(
        profile=RuntimeProfile.STANDARD_LIVE,
        research_stack=False,
        cognitive_runtime="disabled",
        federated_cognitive_mesh="disabled",
        epistemic_integrity="disabled",
        operator_signal_hub="active",
        autonomous_runtime="passive",
        operations_platform="active",
        live_ops_stack=True,
        ops_certification=True,
        rc1_stack=True,
        ga_ops=False,
        post_ga=False,
        ops_evolution=False,
        platform_stack=False,
        ops_playbook=True,
        live_deploy_stack=True,
        week1_stack=True,
        operational_memory=True,
        go_live_stack=True,
        digest_scheduler=True,
        analytics_scheduler=True,
        telegram_ingestion=True,
        story_maintenance=True,
        cluster_coordinator=False,
        openai_daily_aggregate=True,
        burnin_auto_start=False,
        ops_loop_interval_sec=180,
        passive_loop_interval_sec=120,
        max_background_tasks=20,
    )


_caps: RuntimeCapabilities | None = None


def get_runtime_capabilities() -> RuntimeCapabilities:
    global _caps
    if _caps is None:
        _caps = capabilities_for(resolve_runtime_profile())
    return _caps


def loop_enabled(mode: LoopMode) -> bool:
    return mode != "disabled"


def loop_active(mode: LoopMode) -> bool:
    return mode == "active"


def reset_runtime_capabilities_cache() -> None:
    """Clear cached profile (tests and env reload)."""
    global _caps
    _caps = None


def is_loop_enabled_in_profile(
    loop_name: str,
    caps: RuntimeCapabilities | None = None,
) -> bool:
    from bot.runtime.loop_manifest import loops_eligible_for_watchdog

    c = caps or get_runtime_capabilities()
    return loop_name in loops_eligible_for_watchdog(c)


def filter_watchdog_stalled_names(
    names: list[str],
    *,
    caps: RuntimeCapabilities | None = None,
    registry: Any | None = None,
) -> list[str]:
    """Drop stale/zombie stalled entries: disabled profile loops or missing live tasks."""
    from bot.observability.loop_registry import get_loop_registry, loop_task_is_running

    c = caps or get_runtime_capabilities()
    reg = registry or get_loop_registry()
    out: list[str] = []
    for name in names:
        if not is_loop_enabled_in_profile(name, c):
            continue
        if name not in reg.snapshot():
            continue
        if not loop_task_is_running(name):
            continue
        out.append(name)
    return out


def startup_summary_text(caps: RuntimeCapabilities | None = None) -> str:
    c = caps or get_runtime_capabilities()

    def line(name: str, mode: LoopMode | bool) -> str:
        if isinstance(mode, bool):
            return f"  • {name}: {'on' if mode else 'off'}"
        return f"  • {name}: {mode}"

    active = [
        "Telegram operator",
        "controlled_live (canary/freeze/rollback/trace)",
        "publish_guard + metrics snapshots",
        "RSS ingestion (rate-limited)",
        "health watchdog",
    ]
    if c.production_safety:
        active.append("production_safety")
    if c.reliability_layer:
        active.append("reliability (lightweight)")

    passive: list[str] = []
    if c.autonomous_runtime == "passive":
        passive.append(f"autonomous-runtime (heartbeat {c.passive_loop_interval_sec}s)")

    disabled = [
        "federated-cognitive-mesh",
        "epistemic-integrity",
        "cognitive-runtime",
        "operator-signal-hub",
        "research operations-platform tick",
        "live_ops / ops_cert / ga_ops / opmem stacks",
    ]
    lines = [
        f"<b>Runtime profile: {c.profile.value}</b>",
        "",
        "<b>ACTIVE</b>",
    ]
    lines.extend(f"  • {x}" for x in active)
    if passive:
        lines.extend(["", "<b>PASSIVE</b>"])
        lines.extend(f"  • {x}" for x in passive)
    lines.extend(["", "<b>DISABLED</b>"])
    lines.extend(f"  • {x}" for x in disabled)
    lines.append("")
    lines.append(
        f"Ops tick interval: {c.ops_loop_interval_sec}s · "
        f"max background tasks target: {c.max_background_tasks}",
    )
    return "\n".join(lines)


def log_startup_summary() -> None:
    import logging

    from bot.observability.loop_registry import get_loop_registry
    from bot.runtime.loop_manifest import runtime_loops_classification

    caps = get_runtime_capabilities()
    log = logging.getLogger(__name__)
    text = startup_summary_text(caps)
    for block in text.replace("<b>", "").replace("</b>", "").split("\n"):
        if block.strip():
            log.info("event=runtime_profile %s", block.strip())

    classified = runtime_loops_classification(caps)
    reg = get_loop_registry()
    registered = sorted(reg.snapshot().keys())
    log.info(
        "event=runtime_profile_loaded profile=%s",
        caps.profile.value,
    )
    if registered:
        log.info(
            "event=runtime_loops_registered loops=%s",
            ", ".join(registered),
        )
    monitored = sorted(reg.runtime_loops_view(caps)["watchdog_monitored"])
    if monitored:
        log.info(
            "event=runtime_loops_watchdog_monitored loops=%s",
            ", ".join(monitored),
        )
    if classified["disabled"]:
        log.info(
            "event=runtime_loops_disabled_not_registered loops=%s",
            ", ".join(classified["disabled"]),
        )
