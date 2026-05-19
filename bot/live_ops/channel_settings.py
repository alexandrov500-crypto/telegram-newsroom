from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class LiveMode(str, Enum):
    SHADOW = "shadow"
    CANARY = "canary"
    SUPERVISED_LIVE = "supervised_live"
    AUTONOMOUS_LIVE = "autonomous_live"


@dataclass(frozen=True)
class ControlledLiveSettings:
    enabled: bool = False
    live_mode: LiveMode = LiveMode.SHADOW
    canary_max_per_hour: int = 6
    canary_whitelist_topics: tuple[str, ...] = ()
    canary_whitelist_sources: tuple[str, ...] = ()
    allowed_sources: tuple[str, ...] = ()
    safe_hours_start: int = 6
    safe_hours_end: int = 22
    safe_hours_only: bool = False
    cooldown_after_failures_sec: int = 900
    failure_threshold_pause: int = 3
    anomaly_spike_threshold: int = 5
    mandatory_approval_supervised: bool = True
    mandatory_approval_canary: bool = True
    freeze_on_anomaly: bool = True
    enable_rollback: bool = True
    source_quarantine_threshold: int = 3
    source_quarantine_hours: int = 6
    metrics_snapshot_interval_sec: float = 300.0
    public_channel_id: int | None = None
    ops_channel_id: int | None = None
    shadow_channel_id: int | None = None

    @classmethod
    def from_env(cls) -> ControlledLiveSettings:
        enabled = os.getenv("CONTROLLED_LIVE_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("LIVE_DEPLOY_ENABLED", "true").lower() not in (
                "0",
                "false",
                "no",
            )
        mode_raw = os.getenv("LIVE_MODE", "shadow").lower().strip()
        try:
            mode = LiveMode(mode_raw)
        except ValueError:
            mode = LiveMode.SHADOW
        topics = tuple(
            t.strip()
            for t in os.getenv("LIVE_CANARY_TOPICS", "").split(",")
            if t.strip()
        )
        sources = tuple(
            s.strip().lower()
            for s in (
                os.getenv("LIVE_ALLOWED_SOURCES", "")
                or os.getenv("LIVE_CANARY_SOURCES", "")
            ).split(",")
            if s.strip()
        )
        return cls(
            enabled=enabled,
            live_mode=mode,
            canary_max_per_hour=int(os.getenv("LIVE_CANARY_MAX_PER_HOUR", "3")),
            canary_whitelist_topics=topics,
            canary_whitelist_sources=sources,
            allowed_sources=sources,
            safe_hours_start=int(os.getenv("LIVE_SAFE_HOURS_START", "6")),
            safe_hours_end=int(os.getenv("LIVE_SAFE_HOURS_END", "22")),
            safe_hours_only=os.getenv("LIVE_SAFE_HOURS_ONLY", "").lower()
            in ("1", "true", "yes"),
            cooldown_after_failures_sec=int(os.getenv("LIVE_COOLDOWN_SEC", "900")),
            failure_threshold_pause=int(os.getenv("LIVE_FAILURE_PAUSE_THRESHOLD", "3")),
            anomaly_spike_threshold=int(os.getenv("LIVE_ANOMALY_SPIKE", "5")),
            mandatory_approval_supervised=os.getenv(
                "LIVE_SUPERVISED_APPROVAL",
                "true",
            ).lower()
            not in ("0", "false", "no"),
            mandatory_approval_canary=os.getenv("LIVE_CANARY_APPROVAL", "true").lower()
            not in ("0", "false", "no"),
            freeze_on_anomaly=os.getenv("LIVE_FREEZE_ON_ANOMALY", "true").lower()
            not in ("0", "false", "no"),
            enable_rollback=os.getenv("LIVE_ENABLE_ROLLBACK", "true").lower()
            not in ("0", "false", "no"),
            source_quarantine_threshold=int(os.getenv("LIVE_SOURCE_BAD_THRESHOLD", "3")),
            source_quarantine_hours=int(os.getenv("LIVE_SOURCE_COOLDOWN_HOURS", "6")),
            metrics_snapshot_interval_sec=float(
                os.getenv("LIVE_METRICS_INTERVAL_SEC", "300"),
            ),
            public_channel_id=_int_env("LIVE_PUBLIC_CHANNEL_ID")
            or _int_env("TELEGRAM_CHANNEL_ID"),
            ops_channel_id=_int_env("LIVE_OPS_CHANNEL_ID")
            or _int_env("TELEGRAM_OPERATOR_CHAT_ID"),
            shadow_channel_id=_int_env("LIVE_SHADOW_CHANNEL_ID")
            or _int_env("TELEGRAM_DIGEST_CHANNEL_ID"),
        )


def _int_env(key: str) -> int | None:
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
