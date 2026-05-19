from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConfigEntry:
    key: str
    value: str
    source: str
    default: str | None = None


@dataclass
class NewsroomConfigRegistry:
    """Centralized typed config snapshot — explicit values, no silent fallbacks."""

    build_id: str
    entries: dict[str, ConfigEntry] = field(default_factory=dict)

    @classmethod
    def collect(cls, *, build_id: str) -> NewsroomConfigRegistry:
        reg = cls(build_id=build_id)
        keys = (
            ("APP_ENV", os.getenv("APP_ENV", "development"), "development"),
            ("RC1_LOCKDOWN_MODE", os.getenv("RC1_LOCKDOWN_MODE", "false"), "false"),
            ("RC1_ENABLED", os.getenv("RC1_ENABLED", ""), ""),
            ("LIVE_OPS_ENABLED", os.getenv("LIVE_OPS_ENABLED", ""), ""),
            ("OPS_CERT_ENABLED", os.getenv("OPS_CERT_ENABLED", ""), ""),
            ("OPS_CHAOS_ENABLED", os.getenv("OPS_CHAOS_ENABLED", "false"), "false"),
            ("PRODUCTION_SAFETY_ENABLED", os.getenv("PRODUCTION_SAFETY_ENABLED", ""), ""),
            ("RELIABILITY_LAYER_ENABLED", os.getenv("RELIABILITY_LAYER_ENABLED", ""), ""),
            ("PRODUCTION_ROLLOUT_STAGE", os.getenv("PRODUCTION_ROLLOUT_STAGE", "INTERNAL_SHADOW"), "INTERNAL_SHADOW"),
            ("RELIABILITY_PUBLISH_MODE", os.getenv("RELIABILITY_PUBLISH_MODE", "SHADOW"), "SHADOW"),
            ("SHADOW_PUBLISH_ONLY", os.getenv("SHADOW_PUBLISH_ONLY", "false"), "false"),
            ("STREAM_BACKEND", os.getenv("STREAM_BACKEND", os.getenv("EVENT_BUS_BACKEND", "inmemory")), "inmemory"),
            ("REDIS_ENABLED", os.getenv("REDIS_ENABLED", "false"), "false"),
            ("NEWSROOM_USE_POSTGRES", os.getenv("NEWSROOM_USE_POSTGRES", "false"), "false"),
            ("NEWSROOM_DUAL_WRITE", os.getenv("NEWSROOM_DUAL_WRITE", "false"), "false"),
            ("RECOVERY_MODE", os.getenv("RECOVERY_MODE", "false"), "false"),
            ("DEGRADED_STARTUP", os.getenv("DEGRADED_STARTUP", "false"), "false"),
            ("CLUSTER_ENABLED", os.getenv("CLUSTER_ENABLED", "false"), "false"),
            ("STAGING_MODE", os.getenv("STAGING_MODE", "false"), "false"),
        )
        for key, val, default in keys:
            reg.entries[key] = ConfigEntry(
                key=key,
                value=str(val),
                source="env",
                default=default,
            )
        return reg

    def to_dict(self) -> dict[str, str]:
        return {k: e.value for k, e in self.entries.items()}

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
