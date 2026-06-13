"""Format A/B experiment tests."""

from __future__ import annotations

import pytest

from app.growth.autonomous_robot.format_ab import (
    assign_format_variant,
    evaluate_wire_vs_cb,
    init_format_ab_state,
    lock_format_winner,
)


def _row(fmt: str, fr: float, draft_id: int) -> dict:
    return {
        "draft_id": draft_id,
        "format_profile": fmt,
        "validation_status": "FINAL",
        "actual_forward_rate": fr,
        "actual_engagement": 0.4,
        "actual_err": 0.5,
        "actual_forwards": 5,
        "actual_views": 200,
    }


def test_assign_format_variant_stable(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "format_ab")
    init_format_ab_state(str(tmp_path))
    a = assign_format_variant(draft_id=42, content="test")
    b = assign_format_variant(draft_id=42, content="test")
    assert a == b
    assert a in {"subscriber_wire", "cb_brief"}


def test_evaluate_wire_wins_with_clear_lift() -> None:
    rows = [_row("subscriber_wire", 0.045 + i * 0.0001, i) for i in range(20)]
    rows += [_row("cb_brief", 0.018 + i * 0.0001, 100 + i) for i in range(20)]
    verdict = evaluate_wire_vs_cb(rows)
    assert verdict.meets_threshold
    assert verdict.winner == "subscriber_wire"
    assert (verdict.forward_lift_pct or 0) >= 8.0


def test_evaluate_insufficient_samples() -> None:
    rows = [_row("subscriber_wire", 0.04, 1), _row("cb_brief", 0.02, 2)]
    verdict = evaluate_wire_vs_cb(rows)
    assert not verdict.meets_threshold
    assert verdict.winner is None


def test_lock_winner(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_STATE_DIR", str(tmp_path))
    from app.growth.autonomous_robot.format_ab import FormatAbVerdict

    v = FormatAbVerdict(
        winner="subscriber_wire",
        meets_threshold=True,
        reason="forward_rate_winner",
        wire_sample=20,
        cb_sample=20,
        wire_mean_forward=0.04,
        cb_mean_forward=0.02,
        forward_lift_pct=100.0,
        forward_p_value=0.01,
        effect_size="medium",
    )
    state = lock_format_winner(str(tmp_path), "subscriber_wire", v)
    assert state.get("winner_locked") is True
    assert state.get("winner") == "subscriber_wire"
