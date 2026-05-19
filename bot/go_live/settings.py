from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GoLiveSettings:
    enabled: bool = True
    strict_channel_permissions: bool = True
    startup_publish_probe: bool = True
    shadow_validation_required: bool = True
    multi_operator_fallback: bool = True

    @classmethod
    def from_env(cls) -> GoLiveSettings:
        enabled = os.getenv("GO_LIVE_ENABLED", "true").lower() not in ("0", "false", "no")
        return cls(
            enabled=enabled,
            strict_channel_permissions=os.getenv(
                "GO_LIVE_STRICT_PERMISSIONS",
                "true",
            ).lower()
            not in ("0", "false", "no"),
            startup_publish_probe=os.getenv("GO_LIVE_PUBLISH_PROBE", "true").lower()
            not in ("0", "false", "no"),
            shadow_validation_required=os.getenv("GO_LIVE_SHADOW_VALIDATE", "true").lower()
            not in ("0", "false", "no"),
            multi_operator_fallback=os.getenv("GO_LIVE_MULTI_OPERATOR", "true").lower()
            not in ("0", "false", "no"),
        )
