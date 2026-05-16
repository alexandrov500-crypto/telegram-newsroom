"""AI worker entrypoint (JobKind.AI)."""

from __future__ import annotations

import asyncio
import logging

from worker.job_queue import JobKind

from workers.base import WorkerRole
from workers.bootstrap import init_worker_stack, teardown_worker_stack
from workers.handlers import build_ai_registry
from workers.runtime import WorkerRuntime

logger = logging.getLogger(__name__)


async def _async_main() -> None:
    from ai.openai_client import create_openai_client
    from app.config import load_settings

    settings = load_settings()
    await init_worker_stack(settings)
    openai = create_openai_client(
        settings.openai_api_key,
        timeout=settings.openai_http_timeout_sec,
        max_retries=settings.openai_max_retries,
    )
    registry = build_ai_registry()
    rt = WorkerRuntime(
        settings,
        role=WorkerRole.AI,
        job_kind=JobKind.AI,
        registry=registry,
        openai=openai,
    )
    rt.install_signals()
    try:
        await rt.run_forever()
    finally:
        try:
            await openai.close()
        except Exception:
            logger.exception("ai_worker.openai_close_failed")
        await teardown_worker_stack()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
