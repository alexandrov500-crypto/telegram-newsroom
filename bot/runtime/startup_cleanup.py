from __future__ import annotations

import asyncio
import logging

from bot.runtime.loop_manifest import loop_registration_manifest
from bot.runtime.profile import RuntimeCapabilities

logger = logging.getLogger(__name__)

_RUNTIME_TASK_NAMES = frozenset(
    {
        "pilot-ops",
        "operations-platform",
        "epistemic-integrity",
        "federated-cognitive-mesh",
        "cognitive-runtime",
        "operator-signal-hub",
        "autonomous-runtime",
        "reliability-probe",
        "publish-safety-monitor",
    },
)


async def cancel_disabled_runtime_tasks(caps: RuntimeCapabilities) -> int:
    """Cancel asyncio tasks for loops disabled in the current profile (restart / hot reload)."""
    disabled = frozenset(
        name
        for name, mode, _ in loop_registration_manifest(caps)
        if mode == "disabled"
    )
    if not disabled:
        return 0
    cancelled = 0
    current = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is current or task.done():
            continue
        name = task.get_name()
        if name in disabled:
            task.cancel()
            cancelled += 1
    if cancelled:
        logger.info(
            "event=runtime_startup_cleanup cancelled_tasks=%d names=%s",
            cancelled,
            sorted(disabled),
        )
    return cancelled
