from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from bot.observability.loop_registry import LoopHeartbeatRegistry, get_loop_registry
from bot.operations.recovery_cooldown import RecoveryCooldown

logger = logging.getLogger(__name__)

_recovery_cooldown = RecoveryCooldown()


@dataclass(frozen=True)
class RuntimeSupervisorReport:
    stalled_loops: list[str]
    stalled_tasks: int
    replay_lag_sec: float
    queue_backlog: int
    stuck_approvals: int
    recovery_actions: list[str]


class RuntimeSupervisor:
    """Long-lived runtime checks: stalled loops, backlog, replay lag."""

    def __init__(
        self,
        *,
        loop_registry: LoopHeartbeatRegistry | None = None,
        queue_backlog_fn: Any | None = None,
        replay_lag_fn: Any | None = None,
        stuck_approvals_fn: Any | None = None,
    ) -> None:
        self._loops = loop_registry or get_loop_registry()
        self._queue_backlog_fn = queue_backlog_fn
        self._replay_lag_fn = replay_lag_fn
        self._stuck_approvals_fn = stuck_approvals_fn

    async def probe(self) -> RuntimeSupervisorReport:
        from bot.runtime.profile import filter_watchdog_stalled_names

        stalled = filter_watchdog_stalled_names(
            [lb.name for lb in self._loops.stalled_loops()],
            registry=self._loops,
        )
        stalled_tasks = self._count_stalled_async_tasks()
        backlog = int(self._queue_backlog_fn() if self._queue_backlog_fn else 0)
        replay_lag = float(self._replay_lag_fn() if self._replay_lag_fn else 0.0)
        stuck = int(self._stuck_approvals_fn() if self._stuck_approvals_fn else 0)
        recoveries: list[str] = []

        if stalled:
            try:
                from bot.observability.metrics import (
                    set_stalled_loop_count_metric,
                    set_stalled_task_count,
                )
                from bot.observability.loop_health import record_stalled_loops

                set_stalled_task_count(len(stalled) + stalled_tasks)
                set_stalled_loop_count_metric(len(stalled))
                record_stalled_loops(stalled)
            except Exception:
                pass
            for name in stalled:
                key = f"loop_stalled:{name}"
                if _recovery_cooldown.allow(key):
                    recoveries.append(key)
                    self._loops.mark_recovery(name)
                    try:
                        from bot.runtime.instance import get_runtime_identity

                        ident = get_runtime_identity()
                        iid = ident.runtime_instance_id if ident else "unknown"
                    except Exception:
                        iid = "unknown"
                    logger.warning(
                        "event=runtime_loop_stalled loop=%s runtime_instance_id=%s",
                        name,
                        iid,
                    )
                    try:
                        from bot.ops_forensics.hooks import record_timeline

                        record_timeline(
                            "loop_stalled",
                            severity="warning",
                            details={"loop": name, "runtime_instance_id": iid},
                        )
                    except Exception:
                        pass
                else:
                    try:
                        from bot.observability.loop_health import record_recovery_attempt

                        record_recovery_attempt(suppressed=True)
                    except Exception:
                        pass
                    logger.debug(
                        "event=runtime_loop_stalled_suppressed loop=%s cooldown_sec=%.0f",
                        name,
                        _recovery_cooldown.remaining(key),
                    )

        if backlog > 500:
            recoveries.append("queue_backlog_elevated")

        if replay_lag > 30.0:
            recoveries.append("replay_lag_elevated")

        if stuck > 20:
            recoveries.append("approvals_stuck")

        if recoveries:
            try:
                from bot.observability.loop_health import record_recovery_attempt
                from bot.observability.metrics import (
                    record_runtime_watchdog_restart,
                    set_runtime_recovery_rate,
                )

                for _ in recoveries:
                    record_runtime_watchdog_restart()
                    record_recovery_attempt(suppressed=False)
                from bot.observability.loop_health import get_loop_health

                h = get_loop_health()
                total = h.recovery_attempt_count + h.recovery_suppressed_count
                if total:
                    set_runtime_recovery_rate(h.recovery_attempt_count / total)
            except Exception:
                pass

        return RuntimeSupervisorReport(
            stalled_loops=stalled,
            stalled_tasks=stalled_tasks,
            replay_lag_sec=replay_lag,
            queue_backlog=backlog,
            stuck_approvals=stuck,
            recovery_actions=recoveries,
        )

    @staticmethod
    def _count_stalled_async_tasks() -> int:
        try:
            tasks = [t for t in asyncio.all_tasks() if not t.done()]
            return sum(1 for t in tasks if t.get_name().startswith("stalled-"))
        except Exception:
            return 0

    async def attempt_recovery(self, report: RuntimeSupervisorReport) -> None:
        """Lightweight self-recovery hooks (no process restart)."""
        for action in report.recovery_actions:
            if action.startswith("loop_stalled:"):
                # Yield event loop — helps if a tight loop blocked the scheduler
                await asyncio.sleep(0)
            logger.info("event=runtime_recovery_hook action=%s", action)
            try:
                from bot.ops_forensics.hooks import record_timeline

                record_timeline(
                    "runtime_recovery",
                    severity="info",
                    details={"action": action},
                )
            except Exception:
                pass
