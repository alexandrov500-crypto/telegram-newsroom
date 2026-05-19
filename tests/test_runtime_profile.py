from __future__ import annotations

import os

import pytest

from bot.runtime.profile import (
    RuntimeProfile,
    capabilities_for,
    resolve_runtime_profile,
    startup_summary_text,
)


def test_resolve_minimal_from_canary(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_PROFILE", raising=False)
    monkeypatch.setenv("LIVE_MODE", "canary")
    assert resolve_runtime_profile() == RuntimeProfile.MINIMAL_PILOT


def test_explicit_research_full(monkeypatch) -> None:
    monkeypatch.setenv("RUNTIME_PROFILE", "research_full")
    assert resolve_runtime_profile() == RuntimeProfile.RESEARCH_FULL


def test_minimal_disables_research_loops() -> None:
    caps = capabilities_for(RuntimeProfile.MINIMAL_PILOT)
    assert caps.research_stack is False
    assert caps.cognitive_runtime == "disabled"
    assert caps.epistemic_integrity == "disabled"
    assert caps.operator_signal_hub == "disabled"
    assert caps.live_ops_stack is False


def test_startup_summary_contains_profile() -> None:
    text = startup_summary_text(capabilities_for(RuntimeProfile.MINIMAL_PILOT))
    assert "minimal_pilot" in text
    assert "DISABLED" in text
