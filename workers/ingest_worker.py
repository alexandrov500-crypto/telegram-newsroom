"""Ingest worker entrypoint (JobKind.INGEST)."""

from __future__ import annotations

import asyncio
import logging

from worker.job_queue import JobKind

from workers.base import WorkerRole
from workers.bootstrap import init_worker_stack, teardown_worker_stack
from workers.handlers import build_ingest_registry
from workers.runtime import WorkerRuntime

logger = logging.getLogger(__name__)


async def _async_main() -> None:
    from app.config import load_settings

    settings = load_settings()
    await init_worker_stack(settings)
    registry = build_ingest_registry()
    rt = WorkerRuntime(settings, role=WorkerRole.INGEST, job_kind=JobKind.INGEST, registry=registry)
    rt.install_signals()
    try:
        await rt.run_forever()
    finally:
        await teardown_worker_stack()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
