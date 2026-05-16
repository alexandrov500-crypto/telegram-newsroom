"""DB + Redis + queues + reliable transport for standalone worker processes."""

from __future__ import annotations

import logging
from typing import Any

from worker.job_queue import JobKind
from worker.reliable_transport import get_reliable_transport, init_reliable_transport

logger = logging.getLogger(__name__)


async def init_worker_stack(settings: Any) -> None:
    from db.session import init_db
    from utils.redis_client import init_redis_from_settings
    from worker.job_queue import init_job_queue

    await init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    await init_redis_from_settings(settings)
    await init_job_queue(settings)
    await init_reliable_transport(settings)
    transport = get_reliable_transport()
    vis = int(settings.worker_visibility_sec)
    for k in JobKind:
        n = await transport.recover_stale(k, visibility_sec=vis)
        if n:
            logger.info("worker_stack.startup_recover kind=%s moved=%s", k.value, n)


async def teardown_worker_stack() -> None:
    from db.session import close_db
    from utils.redis_client import close_redis
    from worker.job_queue import close_job_queue
    from worker.reliable_transport import close_reliable_transport

    await close_reliable_transport()
    await close_job_queue()
    await close_redis()
    await close_db()
