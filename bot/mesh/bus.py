from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from bot.mesh.envelope import CognitiveEventEnvelope
from bot.mesh.repository import MeshRepository
from bot.mesh.schema import DEFAULT_MESH_CONFIG

logger = logging.getLogger(__name__)

CognitiveHandler = Callable[[CognitiveEventEnvelope], Awaitable[None]]


class FederatedCognitiveBus:
    """Cognitive coordination layer — separate from operational event bus."""

    def __init__(
        self,
        repository: MeshRepository,
        *,
        node_id: str,
        region: str,
        config: dict[str, Any] | None = None,
        federated_sync: Any | None = None,
    ) -> None:
        self._repo = repository
        self._node_id = node_id
        self._region = region
        self._config = config or DEFAULT_MESH_CONFIG
        self._federated = federated_sync
        self._handlers: dict[str, list[CognitiveHandler]] = {}
        self._storm_count = 0

    def subscribe(self, event_type: str, handler: CognitiveHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(
        self,
        envelope: CognitiveEventEnvelope,
        *,
        require_quorum: bool = False,
    ) -> bool:
        if envelope.lane not in ("gossip", "quorum", "regional", "evaluation", "memory", "learning"):
            envelope = CognitiveEventEnvelope(
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                payload=envelope.payload,
                lane="gossip",
                causation_id=envelope.causation_id,
                correlation_id=envelope.correlation_id,
                node_id=envelope.node_id,
                region=envelope.region,
                partition_key=envelope.partition_key,
                sequence_num=envelope.sequence_num,
                ttl_hops=envelope.ttl_hops,
            )

        if self._repo.has_event(envelope.event_id):
            return False

        budget = self._repo.gossip_budget_remaining(self._node_id, self._region)
        if budget <= 0 and envelope.lane == "gossip":
            logger.debug("event=cognitive_gossip_budget_exhausted node=%s", self._node_id)
            return False

        seq = self._repo.next_sequence(self._node_id, self._region)
        stored = self._repo.record_cognitive_event(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            lane=envelope.lane,
            region=envelope.region,
            origin_node=envelope.node_id,
            payload=envelope.payload,
            causation_id=envelope.causation_id,
            correlation_id=envelope.correlation_id,
            sequence_num=seq,
        )
        if not stored:
            return False

        if envelope.lane == "gossip":
            self._repo.consume_gossip_budget(self._node_id, self._region)
        self._storm_count += 1
        threshold = int(self._config.get("cognitive_storm_threshold", 100))
        if self._storm_count > threshold:
            logger.warning("event=cognitive_storm_throttle count=%d", self._storm_count)

        await self._dispatch_local(envelope)

        if self._federated is not None and envelope.lane in ("quorum", "learning", "memory"):
            sync_key = f"mesh_{envelope.lane}_{envelope.event_type}"
            self._federated.publish(sync_key, envelope.to_dict(sign=False))

        try:
            from bot.observability.metrics import record_mesh_cognitive_event

            record_mesh_cognitive_event(envelope.lane, envelope.event_type)
        except Exception:
            pass
        return True

    async def propagate_gossip(
        self,
        envelopes: list[CognitiveEventEnvelope],
        *,
        max_hops: int | None = None,
    ) -> int:
        hops = max_hops or int(self._config.get("max_propagation_hops", 3))
        propagated = 0
        budget = self._repo.gossip_budget_remaining(self._node_id, self._region)
        limit = min(budget, int(self._config.get("gossip_budget_per_tick", 20)))
        for env in envelopes[:limit]:
            if env.ttl_hops <= 0 or env.node_id == self._node_id:
                continue
            child = CognitiveEventEnvelope(
                event_id=env.event_id,
                event_type=env.event_type,
                payload=dict(env.payload),
                lane="gossip",
                causation_id=env.event_id,
                correlation_id=env.correlation_id,
                node_id=self._node_id,
                region=self._region,
                sequence_num=env.sequence_num,
                ttl_hops=min(env.ttl_hops, hops) - 1,
            )
            if await self.publish(child):
                propagated += 1
        return propagated

    async def ingest_remote(self, data: dict) -> bool:
        try:
            envelope = CognitiveEventEnvelope.from_dict(data, verify=False)
        except (KeyError, ValueError):
            return False
        if envelope.node_id == self._node_id:
            return False
        if self._repo.has_event(envelope.event_id):
            return False
        return await self.publish(envelope)

    async def _dispatch_local(self, envelope: CognitiveEventEnvelope) -> None:
        handlers = self._handlers.get(envelope.event_type, [])
        handlers += self._handlers.get("*", [])
        for handler in handlers:
            try:
                await handler(envelope)
            except Exception:
                logger.exception("event=cognitive_handler_failed type=%s", envelope.event_type)

    def reset_tick_budget(self) -> None:
        self._storm_count = 0
        self._repo.reset_gossip_budget(
            self._node_id,
            self._region,
            int(self._config.get("gossip_budget_per_tick", 20)),
        )
