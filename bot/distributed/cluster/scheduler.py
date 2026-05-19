from __future__ import annotations

import logging

from bot.storage.coordination_repository import CoordinationRepository

logger = logging.getLogger(__name__)


class DistributedScheduler:
    """Lease-based global job ownership (e.g. single digest runner)."""

    def __init__(self, repo: CoordinationRepository, *, node_id: str) -> None:
        self._repo = repo
        self._node_id = node_id

    def try_run_global(self, job_name: str, *, ttl_sec: int = 180) -> bool:
        acquired = self._repo.try_acquire_job(
            job_name,
            node_id=self._node_id,
            ttl_sec=ttl_sec,
        )
        if acquired:
            logger.debug("event=global_job_acquired job=%s node=%s", job_name, self._node_id)
        return acquired

    def release(self, job_name: str) -> bool:
        return self._repo.release_job(job_name, node_id=self._node_id)
