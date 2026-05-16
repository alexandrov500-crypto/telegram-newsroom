from __future__ import annotations

from ai.cost_estimation import estimate_chat_cost_usd


def test_cost_estimate_known_model() -> None:
    c = estimate_chat_cost_usd(model="gpt-4.1-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert c is not None and c > 0


def test_cost_unknown_returns_none() -> None:
    assert estimate_chat_cost_usd(model="unknown-model-xyz", input_tokens=1000, output_tokens=1000) is None
