from __future__ import annotations

import logging
import random
from typing import Any, Awaitable, Callable

from bot.ops_certification.chaos.scenarios import ChaosDrillRunner, ChaosScenario

logger = logging.getLogger(__name__)

_SAFE_DRILLS = (
    ChaosScenario.OPENAI_LATENCY,
    ChaosScenario.COGNITION_DELAY,
    ChaosScenario.WORKER_CRASH,
)


class ChaosDrillScheduler:
    """Optional scheduled low-blast-radius chaos drills."""

    def __init__(self, runner: ChaosDrillRunner) -> None:
        self._runner = runner
        self._last_run_id: str | None = None

    async def maybe_run_scheduled(
        self,
        *,
        tick: int,
        interval_ticks: int = 1440,
        on_rollback: Callable[[str], Awaitable[None]] | None = None,
        safety_check: Callable[[], float] | None = None,
    ) -> Any | None:
        if tick <= 0 or tick % interval_ticks != 0:
            return None
        scenario = random.choice(_SAFE_DRILLS)
        logger.info("event=chaos_scheduled_drill scenario=%s", scenario.value)
        return await self._runner.run(
            scenario,
            on_rollback=on_rollback,
            safety_check=safety_check,
        )
