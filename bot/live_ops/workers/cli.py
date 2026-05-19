"""Standalone horizontal worker entrypoints."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from bot.live_ops.settings import LiveOpsSettings
from bot.live_ops.workers.topology import WorkerMeshRegistry, WorkerRole

logger = logging.getLogger(__name__)

_ROLE_MAP = {
    "ingest": WorkerRole.INGEST,
    "cognition": WorkerRole.COGNITION,
    "publish": WorkerRole.PUBLISH,
    "operator": WorkerRole.OPERATOR,
    "metrics": WorkerRole.METRICS,
    "recovery": WorkerRole.RECOVERY,
}


async def _run_worker(role: WorkerRole, node_id: str, interval: float) -> None:
    registry = WorkerMeshRegistry()
    desc = registry.register(role, node_id, queues=(role.value,))
    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    logger.info("event=worker_started role=%s node=%s", role.value, node_id)
    while not stop.is_set():
        desc.heartbeat(status="healthy")
        await asyncio.sleep(interval)
    desc.heartbeat(status="stopping")
    logger.info("event=worker_stopped role=%s", role.value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Newsroom horizontal worker")
    parser.add_argument(
        "role",
        choices=list(_ROLE_MAP.keys()),
        help="Worker role",
    )
    parser.add_argument("--node-id", default=LiveOpsSettings.from_env().node_id)
    parser.add_argument("--heartbeat-sec", type=float, default=30.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    role = _ROLE_MAP[args.role]
    try:
        asyncio.run(_run_worker(role, args.node_id, args.heartbeat_sec))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
