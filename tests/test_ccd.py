"""Tests for CCD — 7-Day Cognitive Content Design."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.ccd.audience_reality_binding import evaluate_audience_reality_binding
from app.editorial.ccd.balance_controller import evaluate_balance, infer_content_category
from app.editorial.ccd.cognitive_slots import CognitiveSlotType, resolve_cognitive_slot
from app.editorial.ccd.controller import apply_ccd_to_decision, evaluate_weekly_experience_state
from app.editorial.ccd.habit_loop import HabitAnchor, evaluate_habit_loop
from app.editorial.ccd.narrative_spine import evaluate_narrative_spine
from app.editorial.ccd.state import ccd_snapshot, record_ccd_evaluation
from app.editorial.ccd.user_journey_simulator import PersonaType, simulate_persona_journey
from app.editorial.ccd.weekly_experience_map import DailyMode, TimeBand, resolve_weekly_experience_slot


@pytest.fixture(autouse=True)
def _enable_ccd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_CCD_LAYER", "true")


def test_weekly_experience_morning_orientation() -> None:
    slot = resolve_weekly_experience_slot(weekday_name="monday", hour_local=8)
    assert slot.time_band == TimeBand.MORNING
    assert slot.daily_mode == DailyMode.ORIENTATION
    assert slot.cognitive_focus == "macro_reset"


def test_cognitive_slot_signal_on_high_gravity() -> None:
    slot = resolve_cognitive_slot(gravity=85, daily_mode=DailyMode.INTELLIGENCE, time_band=TimeBand.MIDDAY, is_breaking=True)
    assert slot.slot_type == CognitiveSlotType.SIGNAL


def test_audience_binding_rejects_noise() -> None:
    binding = evaluate_audience_reality_binding("Подписывайтесь на наш канал — новости ради новостей")
    assert binding.passes is False
    assert binding.noise_detected is True


def test_audience_binding_passes_decision_post() -> None:
    text = "Fed cut rates. Почему важно: инвесторы пересматривают риск и стратегию."
    binding = evaluate_audience_reality_binding(text)
    assert binding.passes is True
    assert binding.decision_relevance is True


def test_narrative_spine_match() -> None:
    spine = evaluate_narrative_spine("CPI inflation rose above Fed target", active_spine="global_inflation_transition")
    assert spine.matched is True


def test_habit_morning_brief_anchor() -> None:
    habit = evaluate_habit_loop(time_band=TimeBand.MORNING)
    assert habit.anchor == HabitAnchor.MORNING_BRIEF


def test_balance_category_inference() -> None:
    assert infer_content_category("OpenAI released GPT-5") == "ai"


def test_persona_journey_macro_heavy() -> None:
    j = simulate_persona_journey(
        persona=PersonaType.MACRO_HEAVY,
        category="macro",
        binding_score=75,
        experience_fit=0.8,
        posts_today=3,
        substitution_score=70,
    )
    assert j.daily_satisfaction >= 0.5
    assert j.return_probability >= 0.4


def test_evaluate_weekly_experience_state(tmp_path: Path) -> None:
    body = (
        "Fed raised rates on inflation concerns.\n\n"
        "Почему важно: investors reassess macro risk.\n\n"
        "OpenAI sector in focus."
    )
    result = evaluate_weekly_experience_state(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="macro",
        gravity=72,
        substitution_score=68,
        newsroom_tz="Europe/Moscow",
    )
    assert result["enabled"] is True
    assert "weekly_experience_slot" in result
    assert "user_journey_simulation" in result
    assert result["experience_fit"] > 0


def test_apply_ccd_downgrades_weak_fit() -> None:
    decision = {"action": "publish", "format_mode": "context", "reasoning_trace": [], "reject": False}
    ccd = {"enabled": True, "force_digest": True, "experience_fit": 0.3}
    out = apply_ccd_to_decision(decision, ccd, publishing_mode="core")
    assert out["action"] == "digest"
    assert out["force_digest"] is True


def test_ccd_state_tracking(tmp_path: Path) -> None:
    record_ccd_evaluation(
        str(tmp_path),
        category="macro",
        experience_fit=0.75,
        binding_score=80,
        spine_matched=True,
        published=True,
    )
    snap = ccd_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1
