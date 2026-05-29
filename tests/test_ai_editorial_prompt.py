from __future__ import annotations

from ai.editorial import build_system_prompt, normalize_summary_style
from tests.conftest import minimal_test_settings


def test_normalize_summary_style_accepts_premium_newsroom() -> None:
    assert normalize_summary_style("premium-newsroom") == "premium-newsroom"


def test_system_prompt_contains_premium_newsroom_structure() -> None:
    settings = minimal_test_settings(summary_style="premium-newsroom")
    prompt = build_system_prompt(settings)
    assert "premium financial newsroom" in prompt
    assert "hook → что произошло → почему это важно → влияние на рынок → краткий вывод" in prompt
