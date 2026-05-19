from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CostMode(str, Enum):
    NORMAL = "NORMAL"
    COST_SAVING = "COST_SAVING"
    EMERGENCY_LOW_COST = "EMERGENCY_LOW_COST"


class StoryTrustState(str, Enum):
    TRUSTED = "TRUSTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class RolloutStage(str, Enum):
    INTERNAL_SHADOW = "INTERNAL_SHADOW"
    LIMITED_CHANNELS = "LIMITED_CHANNELS"
    LOW_FREQUENCY_PUBLIC = "LOW_FREQUENCY_PUBLIC"
    NORMAL_PRODUCTION = "NORMAL_PRODUCTION"
    HIGH_VOLUME_PRODUCTION = "HIGH_VOLUME_PRODUCTION"


@dataclass(frozen=True)
class PublishSafetyVerdict:
    allowed: bool
    reason: str
    trust_state: StoryTrustState
    rollout_stage: RolloutStage
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TelegramDeliveryStats:
    latency_ms_avg: float
    floodwait_count_hour: int
    failure_count_hour: int
    success_ratio: float
    publish_paused: bool
    operator_override: bool


@dataclass(frozen=True)
class FinancialSnapshot:
    mode: CostMode
    hourly_spend_usd: float
    daily_spend_usd: float
    daily_cap_usd: float
    projected_daily_usd: float
    cost_per_story_usd: float
    anomaly: bool


@dataclass(frozen=True)
class ContainmentSnapshot:
    queue_depth: int
    throttled: bool
    ingest_paused: bool
    memory_pressure: bool
    stuck_tasks: int
    dlq_depth: int
    poison_count: int


@dataclass
class ProductionSafetySnapshot:
    telegram: TelegramDeliveryStats
    financial: FinancialSnapshot
    containment: ContainmentSnapshot
    rollout_stage: RolloutStage
    cost_mode: CostMode
    publish_allowed: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollout_stage": self.rollout_stage.value,
            "cost_mode": self.cost_mode.value,
            "publish_allowed": self.publish_allowed,
            "telegram": {
                "latency_ms_avg": self.telegram.latency_ms_avg,
                "floodwait_count_hour": self.telegram.floodwait_count_hour,
                "success_ratio": self.telegram.success_ratio,
                "publish_paused": self.telegram.publish_paused,
            },
            "financial": {
                "daily_spend_usd": self.financial.daily_spend_usd,
                "projected_daily_usd": self.financial.projected_daily_usd,
                "anomaly": self.financial.anomaly,
            },
            "containment": {
                "queue_depth": self.containment.queue_depth,
                "throttled": self.containment.throttled,
                "dlq_depth": self.containment.dlq_depth,
            },
        }
