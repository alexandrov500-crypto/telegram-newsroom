from __future__ import annotations

import asyncio
import logging
from typing import Any

from bot.distributed.config import ClusterConfig
from bot.distributed.types import NodeStatus
from bot.storage.coordination_repository import CoordinationRepository

logger = logging.getLogger(__name__)

_LEADER_LEASE = "cluster_leader"
_HEARTBEAT_SEC = 15
_LEASE_TTL_SEC = 30


class ClusterCoordinator:
    """Node discovery, heartbeats, leader election, and drain coordination."""

    def __init__(
        self,
        repo: CoordinationRepository,
        config: ClusterConfig,
        *,
        event_bus: Any | None = None,
    ) -> None:
        self._repo = repo
        self._config = config
        self._bus = event_bus
        self._task: asyncio.Task[None] | None = None
        self._draining = False
        self._is_leader = False
        self._leader_changes = 0

    @property
    def node_id(self) -> str:
        return self._config.node_id

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def leader_changes(self) -> int:
        return self._leader_changes

    def start(self) -> None:
        if self._task is not None:
            return
        self._repo.register_node(
            node_id=self._config.node_id,
            role=self._config.node_role,
            region=self._config.node_region,
            status=NodeStatus.STARTING.value,
            metadata={"partitions": list(self._config.partitions)},
        )
        self._task = asyncio.create_task(self._run(), name="cluster-coordinator")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._repo.release_lease(_LEADER_LEASE, node_id=self._config.node_id)
        self._task = None

    def drain(self) -> None:
        self._draining = True
        self._repo.set_node_status(
            node_id=self._config.node_id,
            role=self._config.node_role,
            status=NodeStatus.DRAINING.value,
        )

    def undrain(self) -> None:
        self._draining = False
        self._repo.set_node_status(
            node_id=self._config.node_id,
            role=self._config.node_role,
            status=NodeStatus.HEALTHY.value,
        )

    def list_nodes(self, *, include_stale: bool = False) -> list:
        return self._repo.list_nodes(include_stale=include_stale)

    def current_leader(self) -> str | None:
        return self._repo.current_leader(_LEADER_LEASE)

    def failover_leader(self) -> str | None:
        self._repo.release_lease(_LEADER_LEASE, node_id=self._config.node_id)
        lease = self._repo.try_acquire_lease(
            _LEADER_LEASE,
            node_id=self._config.node_id,
            role=self._config.node_role,
            ttl_sec=_LEASE_TTL_SEC,
        )
        if lease is not None:
            self._is_leader = True
            self._leader_changes += 1
            return self._config.node_id
        return self._repo.current_leader(_LEADER_LEASE)

    def rebalance_partitions(self) -> int:
        nodes = self._repo.list_nodes()
        healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY.value]
        if not healthy:
            return 0
        keys = [p for p in self._config.partitions] or ["global"]
        assigned = 0
        for idx, key in enumerate(keys):
            node = healthy[idx % len(healthy)]
            self._repo.assign_partition(key, node.node_id)
            assigned += 1
        return assigned

    async def _run(self) -> None:
        logger.info(
            "event=cluster_coordinator_started node_id=%s role=%s region=%s",
            self._config.node_id,
            self._config.node_role,
            self._config.node_region,
        )
        try:
            while True:
                status = (
                    NodeStatus.DRAINING.value
                    if self._draining
                    else NodeStatus.HEALTHY.value
                )
                self._repo.heartbeat(
                    node_id=self._config.node_id,
                    role=self._config.node_role,
                    status=status,
                )
                stale = self._repo.mark_offline_stale(stale_sec=120)
                if stale:
                    logger.warning("event=cluster_nodes_marked_offline count=%d", stale)

                lease = self._repo.try_acquire_lease(
                    _LEADER_LEASE,
                    node_id=self._config.node_id,
                    role=self._config.node_role,
                    ttl_sec=_LEASE_TTL_SEC,
                )
                was_leader = self._is_leader
                self._is_leader = lease is not None
                if self._is_leader and not was_leader:
                    self._leader_changes += 1
                    logger.info("event=cluster_leader_acquired node_id=%s", self._config.node_id)
                    try:
                        from bot.observability.metrics import record_cluster_leader_change

                        record_cluster_leader_change()
                    except Exception:
                        pass
                    await self._publish_node_health("leader")
                elif was_leader and not self._is_leader:
                    logger.info("event=cluster_leader_lost node_id=%s", self._config.node_id)
                    try:
                        from bot.observability.metrics import record_cluster_leader_change

                        record_cluster_leader_change()
                    except Exception:
                        pass

                for part in self._config.partitions:
                    self._repo.assign_partition(part, self._config.node_id)

                await asyncio.sleep(_HEARTBEAT_SEC)
        except asyncio.CancelledError:
            logger.info("event=cluster_coordinator_stopped")
            raise

    async def _publish_node_health(self, reason: str) -> None:
        if self._bus is None:
            return
        try:
            from bot.events.types import node_health_changed

            await self._bus.publish(
                node_health_changed(
                    node_id=self._config.node_id,
                    status=NodeStatus.HEALTHY.value,
                    is_leader=self._is_leader,
                    reason=reason,
                ),
            )
        except Exception:
            logger.exception("event=node_health_publish_failed")
