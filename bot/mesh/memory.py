from __future__ import annotations

import hashlib
import logging
from typing import Any

from bot.cognitive.memory import EditorialMemorySystem
from bot.mesh.repository import MeshRepository

logger = logging.getLogger(__name__)


class FederatedCognitiveMemory:
    """Regional memory shards with reconciliation and lineage."""

    def __init__(
        self,
        mesh_repo: MeshRepository,
        local_memory: EditorialMemorySystem,
        *,
        node_id: str,
        region: str,
        replication_factor: int = 2,
    ) -> None:
        self._mesh = mesh_repo
        self._local = local_memory
        self._node_id = node_id
        self._region = region
        self._replication_factor = replication_factor

    @staticmethod
    def shard_id(region: str, memory_id: str) -> str:
        return hashlib.sha256(f"{region}:{memory_id}".encode()).hexdigest()[:24]

    def replicate(
        self,
        *,
        memory_id: str,
        payload: dict[str, Any],
        source_region: str | None = None,
    ) -> str:
        region = source_region or self._region
        sid = self.shard_id(region, memory_id)
        clock = self._increment_clock(memory_id, region)
        self._mesh.upsert_memory_shard(
            shard_id=sid,
            region=region,
            memory_id=memory_id,
            payload=payload,
            vector_clock=clock,
            node_id=self._node_id,
            action="replicate",
        )
        return sid

    def _increment_clock(self, memory_id: str, region: str) -> dict[str, int]:
        shards = self._mesh.get_memory_shards(memory_id)
        clock: dict[str, int] = {}
        for s in shards:
            for k, v in s.get("vector_clock", {}).items():
                clock[k] = max(clock.get(k, 0), int(v))
        clock[f"{region}:{self._node_id}"] = clock.get(f"{region}:{self._node_id}", 0) + 1
        return clock

    def reconcile(self, memory_id: str) -> dict[str, Any]:
        shards = self._mesh.get_memory_shards(memory_id)
        if not shards:
            return {"status": "missing", "memory_id": memory_id}
        if len(shards) == 1:
            return {"status": "single_shard", "winner": shards[0]}

        clocks = [s.get("vector_clock", {}) for s in shards]
        winner = self._pick_winner(shards, clocks)
        conflicts = [s for s in shards if s["shard_id"] != winner["shard_id"]]
        return {
            "status": "reconciled" if not conflicts else "divergent",
            "memory_id": memory_id,
            "winner_region": winner["region"],
            "winner_shard": winner["shard_id"],
            "conflict_count": len(conflicts),
            "explanation": self._explain_reconciliation(winner, conflicts),
        }

    @staticmethod
    def _pick_winner(shards: list[dict], clocks: list[dict]) -> dict:
        def dominance(a: dict, b: dict) -> bool:
            a_keys = set(a.keys())
            b_keys = set(b.keys())
            return all(a.get(k, 0) >= b.get(k, 0) for k in b_keys | a_keys) and any(
                a.get(k, 0) > b.get(k, 0) for k in b_keys
            )

        for i, ca in enumerate(clocks):
            dominated_all = True
            for j, cb in enumerate(clocks):
                if i != j and not dominance(ca, cb):
                    dominated_all = False
                    break
            if dominated_all:
                return shards[i]
        return max(shards, key=lambda s: sum(s.get("vector_clock", {}).values()))

    @staticmethod
    def _explain_reconciliation(winner: dict, conflicts: list[dict]) -> str:
        if not conflicts:
            return f"single dominant shard in {winner['region']}"
        regions = sorted({c["region"] for c in conflicts})
        return f"merged via vector clock; divergent regions: {', '.join(regions)}"

    def rollback_memory(self, memory_id: str, *, to_region: str) -> bool:
        shards = [s for s in self._mesh.get_memory_shards(memory_id) if s["region"] == to_region]
        if not shards:
            return False
        winner = shards[0]
        self.replicate(memory_id=memory_id, payload=winner["payload"], source_region=to_region)
        return True

    def sync_from_local(self, *, story_id: int, title: str, summary: str | None) -> str:
        mid = self._local.remember_story(story_id=story_id, title=title, summary=summary)
        return self.replicate(memory_id=mid, payload={"story_id": story_id, "title": title})
