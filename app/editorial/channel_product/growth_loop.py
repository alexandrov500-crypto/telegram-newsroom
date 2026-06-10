"""Telegram-native growth loop — Awareness → ReferenceForward → Return → Habit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GrowthLoopStage(str, Enum):
    AWARENESS = "awareness"
    REFERENCE_FORWARD = "reference_forward"
    RETURN = "return"
    HABIT = "habit"


@dataclass(frozen=True)
class TelegramGrowthLoop:
    stage: GrowthLoopStage
    goal: str
    mechanic: str
    telegram_native: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "goal": self.goal,
            "mechanic": self.mechanic,
            "telegram_native": self.telegram_native,
        }


_LOOPS: dict[GrowthLoopStage, TelegramGrowthLoop] = {
    GrowthLoopStage.AWARENESS: TelegramGrowthLoop(
        stage=GrowthLoopStage.AWARENESS,
        goal="discover_channel",
        mechanic="flagship_headline + #MustRead density",
        telegram_native="channel_preview + search hashtags",
    ),
    GrowthLoopStage.REFERENCE_FORWARD: TelegramGrowthLoop(
        stage=GrowthLoopStage.REFERENCE_FORWARD,
        goal="peer_recommendation",
        mechanic="decision-relevant synthesis + share nudge",
        telegram_native="forward_to_colleague + saved_messages",
    ),
    GrowthLoopStage.RETURN: TelegramGrowthLoop(
        stage=GrowthLoopStage.RETURN,
        goal="daily_reopen",
        mechanic="open_loop + narrative continuity",
        telegram_native="notification_reopen + thread_memory",
    ),
    GrowthLoopStage.HABIT: TelegramGrowthLoop(
        stage=GrowthLoopStage.HABIT,
        goal="replace_other_feeds",
        mechanic="single_feed_substitution + digest rhythm",
        telegram_native="pin_digest + morning_slot",
    ),
}


def classify_growth_loop(
    *,
    ueos_total: float = 0.0,
    flagship: bool = False,
    virality_score: float = 0.0,
    forwardability: float = 0.0,
    is_digest: bool = False,
    anti_pause: bool = False,
) -> TelegramGrowthLoop:
    if anti_pause or is_digest:
        return _LOOPS[GrowthLoopStage.HABIT]
    if flagship or ueos_total >= 88:
        return _LOOPS[GrowthLoopStage.AWARENESS]
    if virality_score >= 65 or forwardability >= 0.55:
        return _LOOPS[GrowthLoopStage.REFERENCE_FORWARD]
    if ueos_total >= 70:
        return _LOOPS[GrowthLoopStage.RETURN]
    return _LOOPS[GrowthLoopStage.REFERENCE_FORWARD]
