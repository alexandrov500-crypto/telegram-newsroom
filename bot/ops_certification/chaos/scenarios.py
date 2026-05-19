from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class ChaosScenario(str, Enum):
    REDIS_OUTAGE = "redis_outage"
    TELEGRAM_TIMEOUT = "telegram_timeout"
    OPENAI_LATENCY = "openai_latency"
    WORKER_CRASH = "worker_crash"
    QUEUE_CORRUPTION = "queue_corruption"
    COGNITION_DELAY = "cognition_delay"
    REPLAY_CORRUPTION = "replay_corruption"
    NETWORK_PARTITION = "network_partition"


@dataclass
class ChaosInjectionState:
    active_scenario: ChaosScenario | None = None
    started_at: float = 0.0
    flags: dict[str, Any] = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.active_scenario is not None

    def clear(self) -> None:
        self.active_scenario = None
        self.flags.clear()


# Module-level injection surface (read by adapters / drills)
chaos_state = ChaosInjectionState()


Injector = Callable[[], Awaitable[dict[str, Any]]]


async def _inject_redis_outage() -> dict[str, Any]:
    chaos_state.flags["redis_unavailable"] = True
    await asyncio.sleep(0.05)
    return {"simulated": "redis_ping_fail", "duration_sec": 2}


async def _inject_telegram_timeout() -> dict[str, Any]:
    chaos_state.flags["telegram_timeout_ms"] = 8000
    return {"simulated": "telegram_slow", "timeout_ms": 8000}


async def _inject_openai_latency() -> dict[str, Any]:
    chaos_state.flags["openai_delay_sec"] = 3.0
    await asyncio.sleep(0.1)
    return {"simulated": "openai_latency", "delay_sec": 3.0}


async def _inject_worker_crash() -> dict[str, Any]:
    chaos_state.flags["worker_crash_simulated"] = True
    return {"simulated": "worker_heartbeat_lost"}


async def _inject_queue_corruption() -> dict[str, Any]:
    chaos_state.flags["queue_corrupt_probe"] = True
    return {"simulated": "queue_checksum_mismatch"}


async def _inject_cognition_delay() -> dict[str, Any]:
    chaos_state.flags["cognition_delay_sec"] = 5.0
    await asyncio.sleep(0.2)
    return {"simulated": "cognition_stall", "delay_sec": 5}


async def _inject_replay_corruption() -> dict[str, Any]:
    chaos_state.flags["replay_integrity_fail"] = True
    return {"simulated": "replay_hash_mismatch"}


async def _inject_network_partition() -> dict[str, Any]:
    chaos_state.flags["partition_node_isolated"] = True
    return {"simulated": "partial_partition", "isolated_nodes": 1}


SCENARIO_INJECTORS: dict[ChaosScenario, Injector] = {
    ChaosScenario.REDIS_OUTAGE: _inject_redis_outage,
    ChaosScenario.TELEGRAM_TIMEOUT: _inject_telegram_timeout,
    ChaosScenario.OPENAI_LATENCY: _inject_openai_latency,
    ChaosScenario.WORKER_CRASH: _inject_worker_crash,
    ChaosScenario.QUEUE_CORRUPTION: _inject_queue_corruption,
    ChaosScenario.COGNITION_DELAY: _inject_cognition_delay,
    ChaosScenario.REPLAY_CORRUPTION: _inject_replay_corruption,
    ChaosScenario.NETWORK_PARTITION: _inject_network_partition,
}


@dataclass
class ChaosRunResult:
    run_id: str
    scenario: ChaosScenario
    status: str
    survivability_score: float
    detail: dict[str, Any]
    aborted: bool = False
    rollback_triggered: bool = False

    def summary(self) -> str:
        emoji = "✅" if self.status == "passed" else "⛔"
        lines = [
            f"<b>{emoji} Chaos drill</b> <code>{self.scenario.value}</code>",
            f"Run: <code>{self.run_id[:12]}</code> · score {self.survivability_score:.2f}",
            f"Status: {self.status}",
        ]
        if self.rollback_triggered:
            lines.append("↩️ Auto-rollback triggered")
        if self.aborted:
            lines.append("🛑 Safety stop")
        return "\n".join(lines)


@dataclass
class ChaosDrillRunner:
    """Controlled chaos with safety stops and survivability scoring."""

    min_survivability: float = 0.55
    auto_rollback_below: float = 0.4

    async def run(
        self,
        scenario: ChaosScenario,
        *,
        on_rollback: Callable[[str], Awaitable[None]] | None = None,
        safety_check: Callable[[], float] | None = None,
    ) -> ChaosRunResult:
        run_id = str(uuid.uuid4())
        injector = SCENARIO_INJECTORS.get(scenario)
        if injector is None:
            return ChaosRunResult(
                run_id=run_id,
                scenario=scenario,
                status="unknown_scenario",
                survivability_score=0.0,
                detail={},
            )

        chaos_state.active_scenario = scenario
        chaos_state.started_at = time.monotonic()
        detail: dict[str, Any] = {}
        aborted = False
        rollback = False

        try:
            detail = await injector()
            base_score = 0.85
            if chaos_state.flags.get("replay_integrity_fail"):
                base_score -= 0.15
            if safety_check is not None:
                health = safety_check()
                base_score = min(base_score, health)
            if base_score < self.min_survivability:
                aborted = True
                detail["safety_stop"] = "survivability_below_threshold"
            if base_score < self.auto_rollback_below and on_rollback is not None:
                rollback = True
                await on_rollback(f"chaos_{scenario.value}")
                detail["rollback"] = True
            status = "passed" if base_score >= self.min_survivability and not aborted else "failed"
            return ChaosRunResult(
                run_id=run_id,
                scenario=scenario,
                status=status,
                survivability_score=base_score,
                detail=detail,
                aborted=aborted,
                rollback_triggered=rollback,
            )
        finally:
            chaos_state.clear()

    def list_scenarios(self) -> list[str]:
        return [s.value for s in ChaosScenario]
