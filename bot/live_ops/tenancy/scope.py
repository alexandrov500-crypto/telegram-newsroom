from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.production_safety.types import RolloutStage


@dataclass(frozen=True)
class ChannelScope:
    """Per-channel config foundation (multi-tenant ready, single-tenant default)."""

    channel_id: int
    tenant_id: str = "default"
    rollout_stage: RolloutStage = RolloutStage.INTERNAL_SHADOW
    daily_budget_usd: float = 50.0
    trust_policy: str = "standard"
    cognition_strategy: str = "balanced"
    publish_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantRegistry:
    """In-memory tenant/channel registry — not full SaaS."""

    _channels: dict[int, ChannelScope] = field(default_factory=dict)

    def register(self, scope: ChannelScope) -> None:
        self._channels[scope.channel_id] = scope

    def get(self, channel_id: int) -> ChannelScope | None:
        return self._channels.get(channel_id)

    def default_for_channel(self, channel_id: int) -> ChannelScope:
        return self._channels.get(channel_id) or ChannelScope(channel_id=channel_id)

    def list_tenants(self) -> list[str]:
        return sorted({c.tenant_id for c in self._channels.values()} or {"default"})
