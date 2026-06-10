"""CCD controller — evaluate weekly experience state."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.editorial.ccd.audience_reality_binding import evaluate_audience_reality_binding
from app.editorial.ccd.balance_controller import evaluate_balance, infer_content_category
from app.editorial.ccd.cognitive_slots import resolve_cognitive_slot
from app.editorial.ccd.config import ccd_enabled, weekly_experience_min_fit
from app.editorial.ccd.habit_loop import evaluate_habit_loop
from app.editorial.ccd.narrative_spine import active_spine_for_week, evaluate_narrative_spine
from app.editorial.ccd.state import record_ccd_evaluation
from app.editorial.ccd.user_journey_simulator import PersonaType, simulate_all_personas
from app.editorial.ccd.weekly_experience_map import resolve_weekly_experience_slot


def evaluate_weekly_experience_state(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str = "",
    gravity: float = 50.0,
    substitution_score: float = 50.0,
    is_breaking: bool = False,
    newsroom_tz: str = "Europe/Moscow",
) -> dict[str, Any]:
    if not ccd_enabled():
        return {"enabled": False, "experience_fit": 1.0, "force_digest": False}

    try:
        tz = ZoneInfo(newsroom_tz)
        now = datetime.now(tz)
        weekday = now.strftime("%A").lower()
        hour = now.hour
    except Exception:
        weekday = "monday"
        hour = 12

    slot_map = resolve_weekly_experience_slot(weekday_name=weekday, hour_local=hour)
    cog_slot = resolve_cognitive_slot(
        gravity=gravity,
        daily_mode=slot_map.daily_mode,
        time_band=slot_map.time_band,
        is_breaking=is_breaking,
    )
    binding = evaluate_audience_reality_binding(body)
    spine = evaluate_narrative_spine(body, active_spine=active_spine_for_week(), editorial_category=editorial_category)
    category = infer_content_category(body, editorial_category)
    balance = evaluate_balance(category, runtime_dir=runtime_dir)
    habit = evaluate_habit_loop(
        time_band=slot_map.time_band,
        is_breaking=is_breaking,
        substitution_score=substitution_score,
    )

    cat_match = category in slot_map.preferred_categories or category in ("markets", "macro", "ai", "geopolitics")
    experience_fit = 0.0
    experience_fit += 0.25 if cat_match else 0.05
    experience_fit += 0.25 if binding.passes else 0.0
    experience_fit += 0.20 if spine.matched else 0.05
    experience_fit += 0.15 if balance.within_balance else 0.0
    experience_fit += 0.15 if binding.binding_score >= 60 else 0.05
    experience_fit = min(1.0, experience_fit)

    journey = simulate_all_personas(
        category=category,
        binding_score=binding.binding_score,
        experience_fit=experience_fit,
        posts_today=sum(int(v) for v in ccd_snapshot_counts(runtime_dir).values()),
        substitution_score=substitution_score,
    )

    force_digest = False
    merge_suggested = False
    if not spine.matched and experience_fit < weekly_experience_min_fit():
        force_digest = True
        merge_suggested = spine.merge_suggested
    if balance.defer_category:
        force_digest = True
    if not binding.passes and not is_breaking:
        force_digest = True

    record_ccd_evaluation(
        runtime_dir,
        category=category,
        experience_fit=experience_fit,
        binding_score=binding.binding_score,
        spine_matched=spine.matched,
        published=False,
    )

    return {
        "enabled": True,
        "weekly_experience_slot": slot_map.to_dict(),
        "cognitive_slot": cog_slot.to_dict(),
        "audience_reality_binding": binding.to_dict(),
        "narrative_spine": spine.to_dict(),
        "balance": balance.to_dict(),
        "habit_loop": habit.to_dict(),
        "user_journey_simulation": journey,
        "experience_fit": round(experience_fit, 3),
        "force_digest": force_digest,
        "merge_suggested": merge_suggested,
        "category": category,
        "objective": "weekly_cognitive_experience_engine",
    }


def ccd_snapshot_counts(runtime_dir: str | None) -> dict[str, int]:
    from app.editorial.ccd.state import load_state

    import time

    day_key = time.strftime("%Y-%m-%d", time.gmtime())
    day = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    return dict(day.get("category_counts") or {})


def apply_ccd_to_decision(
    decision_dict: dict[str, Any],
    ccd: dict[str, Any],
    *,
    publishing_mode: str = "core",
) -> dict[str, Any]:
    """Adjust OSGCP decision based on CCD weekly experience fit (priority 5)."""
    if not ccd.get("enabled"):
        return decision_dict

    trace = list(decision_dict.get("reasoning_trace") or [])
    force_digest = bool(ccd.get("force_digest"))
    fit = float(ccd.get("experience_fit") or 0)

    if force_digest and not decision_dict.get("stability_override"):
        trace.append("ccd:weekly_experience_downgrade")
        decision_dict = {
            **decision_dict,
            "action": "digest",
            "format_mode": "digest",
            "force_digest": True,
            "reject": False,
            "reasoning_trace": trace,
        }
    elif fit < weekly_experience_min_fit() and publishing_mode == "core":
        if decision_dict.get("action") == "reject":
            trace.append("ccd:experience_fit_digest_fallback")
            decision_dict = {
                **decision_dict,
                "action": "digest",
                "format_mode": "digest",
                "force_digest": True,
                "reject": False,
                "reasoning_trace": trace,
            }

    return decision_dict
