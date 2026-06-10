"""Telegram-native growth mechanics v2 — reference, return, habit loops."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.product_os.content_format import ContentFormat
from app.editorial.product_os.replacement_loop import ReplacementStage


@dataclass(frozen=True)
class TelegramMechanics:
    reference_loop: dict[str, Any]
    return_loop: dict[str, Any]
    habit_loop: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_loop": self.reference_loop,
            "return_loop": self.return_loop,
            "habit_loop": self.habit_loop,
        }


def build_telegram_mechanics(
    *,
    content_format: ContentFormat,
    replacement_stage: ReplacementStage,
    pg_total: float,
    trigger_forward: bool,
    hour_local: int = 12,
) -> TelegramMechanics:
    ref_triggers: list[str] = []
    if trigger_forward:
        ref_triggers.extend(["this_explains_everything", "send_to_colleague"])
    if content_format in {ContentFormat.MODEL, ContentFormat.INSIGHT}:
        ref_triggers.append("save_this")

    ret_triggers: list[str] = []
    if 6 <= hour_local < 11:
        ret_triggers.append("morning_brief_dependency")
    if 17 <= hour_local < 22:
        ret_triggers.append("evening_wrap_closure")
    if pg_total >= 85 and content_format == ContentFormat.SIGNAL:
        ret_triggers.append("breaking_alert_high_pg")

    habit_triggers: list[str] = []
    if content_format == ContentFormat.DIGEST:
        habit_triggers.extend(["consistent_format_timing", "predictable_structure"])
    if replacement_stage in {ReplacementStage.HABIT, ReplacementStage.DEPENDENCY}:
        habit_triggers.append("recurring_rubric")
    if 6 <= hour_local < 10:
        habit_triggers.append("morning_rubric")
    if 18 <= hour_local < 21:
        habit_triggers.append("evening_rubric")

    return TelegramMechanics(
        reference_loop={"active": bool(ref_triggers), "triggers": ref_triggers},
        return_loop={"active": bool(ret_triggers), "triggers": ret_triggers},
        habit_loop={"active": bool(habit_triggers), "triggers": habit_triggers},
    )
