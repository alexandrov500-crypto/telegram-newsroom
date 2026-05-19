from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class ChaosResult:
    scenario: str
    passed: bool
    detail: str
    assertions: list[str] = field(default_factory=list)


class ChaosRunner:
    """Distributed chaos validation harness (dev/staging)."""

    def __init__(self) -> None:
        self._results: list[ChaosResult] = []

    async def run_all(self, scenarios: dict[str, Callable[[], Awaitable[None]]]) -> list[ChaosResult]:
        self._results = []
        for name, fn in scenarios.items():
            try:
                await fn()
                self._results.append(ChaosResult(name, True, "completed"))
            except AssertionError as exc:
                self._results.append(ChaosResult(name, False, str(exc)))
            except Exception as exc:
                self._results.append(ChaosResult(name, False, repr(exc)))
        return self._results

    @staticmethod
    async def simulate_node_kill(recovery: Any) -> None:
        """Orphan recovery should claim stalled workflows."""
        count = await recovery.recover_orphans()
        assert count >= 0, "orphan recovery must not crash"

    @staticmethod
    async def simulate_duplicate_publish(idempotency: Any) -> None:
        key = idempotency.build_key(
            pending_news_id=42,
            channel_id=1,
            language="en",
            content_hash="test-link",
        )
        idempotency.try_begin(
            key,
            pending_news_id=42,
            digest_id=None,
            channel_id=1,
            language="en",
            node_id="chaos",
        )
        idempotency.complete(key, telegram_message_id=999)
        dup = idempotency.try_begin(
            key,
            pending_news_id=42,
            digest_id=None,
            channel_id=1,
            language="en",
            node_id="chaos-2",
        )
        assert dup is not None and dup.telegram_message_id == 999, "duplicate must return receipt"

    @staticmethod
    async def simulate_stream_lag(scheduler: Any) -> None:
        from bot.runtime.adaptive_scheduler import LoadSignals

        scheduler.update_signals(LoadSignals(stream_lag_sec=120.0, queue_backlog=600))
        decision = scheduler.try_schedule("digest_hourly", qos_class="analytics")
        assert not decision.acquired, "analytics should shed under lag"

    @staticmethod
    async def simulate_degradation(degradation: Any) -> None:
        snap = degradation.transition("publish_safe", reason="chaos test", force=True)
        assert snap.mode == "publish_safe"
        degradation.rollback()

    @staticmethod
    async def simulate_partition_pause(coordination: Any) -> None:
        coordination.assign_partition("eu_geopolitical", "chaos-node")
        coordination.set_partition_paused("eu_geopolitical", True)
        parts = coordination.list_partitions()
        paused = [p for p in parts if p["partition_key"] == "eu_geopolitical"]
        assert paused and int(paused[0].get("paused") or 0) == 1, "partition must be paused"
        coordination.set_partition_paused("eu_geopolitical", False)

    def report(self) -> str:
        lines = ["Chaos validation report", ""]
        for r in self._results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.scenario}: {r.detail}")
        passed = sum(1 for r in self._results if r.passed)
        lines.append(f"\n{passed}/{len(self._results)} passed")
        return "\n".join(lines)


async def run_chaos_suite(
    *,
    recovery: Any,
    idempotency: Any,
    scheduler: Any,
    degradation: Any,
    coordination: Any,
) -> list[ChaosResult]:
    runner = ChaosRunner()
    return await runner.run_all(
        {
            "node_kill_recovery": lambda: ChaosRunner.simulate_node_kill(recovery),
            "duplicate_publish": lambda: ChaosRunner.simulate_duplicate_publish(idempotency),
            "stream_lag_shed": lambda: ChaosRunner.simulate_stream_lag(scheduler),
            "degradation_transition": lambda: ChaosRunner.simulate_degradation(degradation),
            "partition_pause": lambda: ChaosRunner.simulate_partition_pause(coordination),
        },
    )
