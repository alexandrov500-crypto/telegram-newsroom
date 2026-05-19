from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from bot.platform.repository import PlatformRepository


@dataclass
class InternalApiGateway:
    """Typed internal APIs with scopes, rate limits, audit."""

    repository: PlatformRepository
    _rate_buckets: dict[str, list[float]] = field(default_factory=dict)
    rate_limit_per_min: int = 120

    def _check_rate(self, client_id: str) -> bool:
        now = time.time()
        bucket = [t for t in self._rate_buckets.get(client_id, []) if now - t < 60]
        if len(bucket) >= self.rate_limit_per_min:
            return False
        bucket.append(now)
        self._rate_buckets[client_id] = bucket
        return True

    async def invoke(
        self,
        endpoint: str,
        *,
        client_id: str,
        scope: str,
        payload: dict[str, Any] | None = None,
        version: str = "v1",
    ) -> dict[str, Any]:
        if not self._check_rate(client_id):
            self.repository.api_audit(endpoint, scope, client_id, 429)
            return {"ok": False, "error": "rate_limited"}
        allowed_scopes = {"read", "write", "admin", "operator"}
        if scope not in allowed_scopes:
            self.repository.api_audit(endpoint, scope, client_id, 403)
            return {"ok": False, "error": "invalid_scope"}
        self.repository.api_audit(endpoint, scope, client_id, 200)
        return {"ok": True, "endpoint": endpoint, "version": version, "data": payload or {}}
