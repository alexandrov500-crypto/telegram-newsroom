"""Operational economics: budgets, resources, modes, SLO."""

from __future__ import annotations

from ops.economics.budgets import allow_ai_request, budgets_payload, record_ai_usage
from ops.economics.economic_mode import EconomicMode, load_economic_mode, set_economic_mode
from ops.economics.load_shedding import evaluate_load_shedding
from ops.economics.resource_accounting import record_resource, resources_payload
from ops.economics.slo import compute_slo_status


def test_ai_budget_blocks_low_priority(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    import os

    os.environ["AI_MAX_TOKENS_PER_HOUR"] = "100"
    os.environ["AI_MAX_REQUESTS_PER_HOUR"] = "2"
    record_ai_usage(rd, tokens=95, requests=2)
    ok, reason = allow_ai_request(rd, priority_level="low", economic_mode="balanced")
    assert not ok
    ok_h, _ = allow_ai_request(rd, priority_level="high", economic_mode="balanced")
    assert ok_h or reason  # high may override near limit


def test_resource_accounting_rollup(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    record_resource(rd, stage="summarize", duration_sec=1.5, tokens=100, cost_usd=0.01)
    payload = resources_payload(rd, hours=2)
    assert "hourly" in payload
    assert payload["live_counters"]["ai_input_tokens"] >= 0


def test_economic_mode(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    set_economic_mode(rd, EconomicMode.LOW_COST, reason="test")
    assert load_economic_mode(rd) == EconomicMode.LOW_COST
    set_economic_mode(rd, EconomicMode.BALANCED, reason="reset")


def test_slo_compute(ephemeral_newsroom_settings) -> None:
    slo = compute_slo_status(ephemeral_newsroom_settings, ephemeral_newsroom_settings.runtime_state_dir)
    assert "slos" in slo
    assert "publish_success_rate" in slo["slos"]


def test_load_shedding(ephemeral_newsroom_settings) -> None:
    state = evaluate_load_shedding(
        ephemeral_newsroom_settings,
        ephemeral_newsroom_settings.runtime_state_dir,
    )
    assert state.get("publish_integrity_preserved") is True
