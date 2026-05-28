"""Controlled public rollout — staged publish limits and stricter thresholds."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


class RolloutStage(str, Enum):
    STAGE_0_PRIVATE_QA = "STAGE_0_PRIVATE_QA"
    STAGE_1_LIMITED_PUBLIC = "STAGE_1_LIMITED_PUBLIC"
    STAGE_2_OBSERVED_PUBLIC = "STAGE_2_OBSERVED_PUBLIC"
    STAGE_3_FULL_AUTONOMOUS = "STAGE_3_FULL_AUTONOMOUS"


@dataclass(frozen=True)
class RolloutStageConfig:
    stage: RolloutStage
    max_publishes_per_hour: int
    auto_publish_allowed: bool
    min_confidence_bump: float
    min_text_chars_bump: int
    alert_continuity_score_min: float
    alert_publish_gap_hours: float
    qa_mirror: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "max_publishes_per_hour": self.max_publishes_per_hour,
            "auto_publish_allowed": self.auto_publish_allowed,
            "min_confidence_bump": self.min_confidence_bump,
            "min_text_chars_bump": self.min_text_chars_bump,
            "alert_continuity_score_min": self.alert_continuity_score_min,
            "alert_publish_gap_hours": self.alert_publish_gap_hours,
            "qa_mirror": self.qa_mirror,
        }


_STAGE_CONFIGS: dict[RolloutStage, RolloutStageConfig] = {
    RolloutStage.STAGE_0_PRIVATE_QA: RolloutStageConfig(
        stage=RolloutStage.STAGE_0_PRIVATE_QA,
        max_publishes_per_hour=2,
        auto_publish_allowed=False,
        min_confidence_bump=0.10,
        min_text_chars_bump=40,
        alert_continuity_score_min=60.0,
        alert_publish_gap_hours=6.0,
        qa_mirror=True,
    ),
    RolloutStage.STAGE_1_LIMITED_PUBLIC: RolloutStageConfig(
        stage=RolloutStage.STAGE_1_LIMITED_PUBLIC,
        max_publishes_per_hour=4,
        auto_publish_allowed=True,
        min_confidence_bump=0.06,
        min_text_chars_bump=20,
        alert_continuity_score_min=52.0,
        alert_publish_gap_hours=7.0,
        qa_mirror=True,
    ),
    RolloutStage.STAGE_2_OBSERVED_PUBLIC: RolloutStageConfig(
        stage=RolloutStage.STAGE_2_OBSERVED_PUBLIC,
        max_publishes_per_hour=8,
        auto_publish_allowed=True,
        min_confidence_bump=0.03,
        min_text_chars_bump=10,
        alert_continuity_score_min=48.0,
        alert_publish_gap_hours=8.0,
        qa_mirror=False,
    ),
    RolloutStage.STAGE_3_FULL_AUTONOMOUS: RolloutStageConfig(
        stage=RolloutStage.STAGE_3_FULL_AUTONOMOUS,
        max_publishes_per_hour=24,
        auto_publish_allowed=True,
        min_confidence_bump=0.0,
        min_text_chars_bump=0,
        alert_continuity_score_min=45.0,
        alert_publish_gap_hours=8.0,
        qa_mirror=False,
    ),
}


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def controlled_rollout_enabled() -> bool:
    return _env_bool("CONTROLLED_PUBLIC_ROLLOUT", "false")


def current_rollout_stage() -> RolloutStage:
    raw = os.getenv("ROLLOUT_STAGE", RolloutStage.STAGE_0_PRIVATE_QA.value).strip().upper()
    try:
        return RolloutStage(raw)
    except ValueError:
        log_event(logger, "controlled_rollout.unknown_stage", stage=raw)
        return RolloutStage.STAGE_0_PRIVATE_QA


def rollout_stage_config(stage: RolloutStage | None = None) -> RolloutStageConfig:
    st = stage or current_rollout_stage()
    return _STAGE_CONFIGS.get(st, _STAGE_CONFIGS[RolloutStage.STAGE_0_PRIVATE_QA])


def rollout_qa_mirror_enabled() -> bool:
    if not controlled_rollout_enabled():
        return False
    return rollout_stage_config().qa_mirror


def effective_auto_publish_min_confidence() -> float:
    raw = os.getenv("AUTO_PUBLISH_MIN_CONFIDENCE", "0.72").strip()
    try:
        base = max(0.5, min(0.99, float(raw)))
    except ValueError:
        base = 0.72
    if not controlled_rollout_enabled():
        return base
    cfg = rollout_stage_config()
    return min(0.99, base + cfg.min_confidence_bump)


def effective_auto_publish_min_text_chars() -> int:
    try:
        base = int(os.getenv("AUTO_PUBLISH_MIN_TEXT_CHARS", "80").strip() or "80")
    except ValueError:
        base = 80
    if not controlled_rollout_enabled():
        return base
    return base + rollout_stage_config().min_text_chars_bump


def effective_alert_thresholds() -> dict[str, float]:
    if not controlled_rollout_enabled():
        return {
            "continuity_score_min": float(os.getenv("ALERT_CONTINUITY_SCORE_MIN", "45")),
            "publish_gap_hours": float(os.getenv("ALERT_PUBLISH_GAP_HOURS", "8")),
        }
    cfg = rollout_stage_config()
    return {
        "continuity_score_min": cfg.alert_continuity_score_min,
        "publish_gap_hours": cfg.alert_publish_gap_hours,
    }


def _hourly_publish_count(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM published_posts
            WHERE published_at >= datetime('now', '-1 hours')
            """
        ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0


def rollout_hourly_publish_count(*, db_path: str | None = None) -> int:
    from utils.database_url import sqlite_path_from_url

    raw = db_path or os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path or not Path(path).is_file():
        return 0
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        return _hourly_publish_count(conn)
    finally:
        conn.close()


def evaluate_rollout_publish_gate(runtime_dir: str | None = None) -> tuple[bool, str]:
    """Stricter publish gate when controlled rollout is active (does not bypass other gates)."""
    if not controlled_rollout_enabled():
        return True, "rollout_off"
    cfg = rollout_stage_config()
    if cfg.max_publishes_per_hour <= 0:
        return False, "rollout_stage_publish_blocked"
    hourly = rollout_hourly_publish_count()
    if hourly >= cfg.max_publishes_per_hour:
        return False, f"rollout_hourly_cap:{hourly}/{cfg.max_publishes_per_hour}"
    return True, "rollout_ok"


def rollout_auto_publish_allowed() -> tuple[bool, str]:
    if not controlled_rollout_enabled():
        return True, "rollout_off"
    cfg = rollout_stage_config()
    if not cfg.auto_publish_allowed:
        return False, "rollout_stage_auto_publish_disabled"
    allowed, reason = evaluate_rollout_publish_gate()
    if not allowed:
        return False, reason
    return True, "rollout_ok"


def rollout_payload() -> dict[str, Any]:
    if not controlled_rollout_enabled():
        return {"enabled": False}
    cfg = rollout_stage_config()
    hourly = rollout_hourly_publish_count()
    return {
        "enabled": True,
        "stage": cfg.stage.value,
        "config": cfg.to_dict(),
        "hourly_publish_count": hourly,
        "hourly_cap_remaining": max(0, cfg.max_publishes_per_hour - hourly),
        "effective_min_confidence": effective_auto_publish_min_confidence(),
        "alert_thresholds": effective_alert_thresholds(),
    }


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "controlled_rollout_state.json"


def touch_rollout_state(runtime_dir: str) -> None:
    """Persist lightweight rollout observability snapshot."""
    if not controlled_rollout_enabled():
        return
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = rollout_payload()
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        log_event(logger, "controlled_rollout.state_write_failed", error=repr(exc)[:120])
