from __future__ import annotations

from dataclasses import dataclass

from app.editorial.staging_mode import (
    evaluate_staging_publish_gate,
    is_final_staging_mode,
    record_staging_publish,
)


@dataclass(frozen=True)
class _Settings:
    final_staging_mode: bool = True
    final_staging_max_publishes_per_hour: int = 2
    runtime_state_dir: str = "/tmp/newsroom_staging_test"


def test_staging_off_allows(monkeypatch) -> None:
    monkeypatch.delenv("FINAL_STAGING_MODE", raising=False)
    v = evaluate_staging_publish_gate(settings=_Settings(final_staging_mode=False))
    assert v.allowed
    assert v.reason == "staging_off"


def test_staging_tier3_requires_manual(tmp_path, monkeypatch) -> None:
    rd = str(tmp_path)
    v = evaluate_staging_publish_gate(
        sources=["@unknown_xyz"],
        runtime_dir=rd,
        settings=_Settings(runtime_state_dir=rd),
        operator_approved=False,
    )
    assert not v.allowed
    assert v.manual_review_required


def test_staging_hourly_cap(tmp_path) -> None:
    rd = str(tmp_path)
    settings = _Settings(runtime_state_dir=rd, final_staging_max_publishes_per_hour=1)
    record_staging_publish(rd)
    v = evaluate_staging_publish_gate(
        sources=["@cb_economics"],
        runtime_dir=rd,
        settings=settings,
        operator_approved=False,
    )
    assert not v.allowed
    assert "staging_hourly_cap" in v.reason


def test_is_final_staging_mode_env(monkeypatch) -> None:
    monkeypatch.setenv("FINAL_STAGING_MODE", "true")
    assert is_final_staging_mode()
