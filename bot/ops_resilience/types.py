from __future__ import annotations

from enum import Enum


class OperationalPosture(str, Enum):
    STABLE = "stable"
    DEGRADED = "degraded"
    PROTECTED = "protected"
    RECOVERY = "recovery"
    OBSERVATION_ONLY = "observation_only"


class DependencyHealthBand(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNSTABLE = "unstable"
    CRITICAL = "critical"


DEPENDENCIES = (
    "telegram_api",
    "rss_ingestion",
    "sqlite",
    "openai_api",
    "filesystem",
    "background_maintenance",
)
