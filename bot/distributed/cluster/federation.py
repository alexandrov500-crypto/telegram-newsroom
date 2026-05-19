from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from bot.distributed.types import StoryVersionVector
from bot.storage.coordination_repository import CoordinationRepository

logger = logging.getLogger(__name__)


class FederatedStoryRegistry:
    """Optimistic story version sync across cluster nodes."""

    def __init__(self, repo: CoordinationRepository, *, node_id: str) -> None:
        self._repo = repo
        self._node_id = node_id

    @staticmethod
    def payload_hash(payload: dict[str, Any]) -> str:
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def get_version(self, story_id: int) -> StoryVersionVector | None:
        return self._repo.get_story_version(story_id)

    def commit_update(
        self,
        *,
        story_id: int,
        expected_version: int | None,
        payload: dict[str, Any],
    ) -> StoryVersionVector | None:
        digest = self.payload_hash(payload)
        result = self._repo.upsert_story_version(
            story_id=story_id,
            node_id=self._node_id,
            expected_version=expected_version,
            payload_hash=digest,
        )
        if result is None:
            logger.warning(
                "event=story_federation_conflict story_id=%s node=%s",
                story_id,
                self._node_id,
            )
        return result
