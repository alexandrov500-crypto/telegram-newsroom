"""Debug publication path: flags, fallback summarizer, AI gating snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from ai.fallback_summarizer import fallback_summarize_cluster
from app.operational_mode import OperationalMode
from app.pipeline_debug import (
    ai_gating_snapshot,
    is_first_post_debug_mode,
    pipeline_debug_active,
)


@dataclass
class _FakePost:
    id: int
    channel_name: str
    message_id: int
    text: str


def _post(pid: int, text: str, ch: str = "ch1") -> _FakePost:
    return _FakePost(id=pid, channel_name=ch, message_id=pid, text=text)


def test_fallback_summarizer_produces_text() -> None:
    posts = [_post(1, "Alpha news one"), _post(2, "Beta news two")]
    res = fallback_summarize_cluster(posts)
    assert res.post_text
    assert res.used_ids
    assert res.execution.model == "rule_fallback"


def test_pipeline_debug_active_force_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORCE_SINGLE_PUBLISH", "true")
    monkeypatch.delenv("RUNTIME_OPERATIONAL_MODE", raising=False)

    class S:
        runtime_state_dir = str(tmp_path)
        force_single_publish = True

    assert pipeline_debug_active(S()) is True


def test_force_single_publish_consumed(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.pipeline_debug import mark_force_single_publish_done

    monkeypatch.setenv("FORCE_SINGLE_PUBLISH", "true")

    class S:
        runtime_state_dir = str(tmp_path)
        force_single_publish = True

    mark_force_single_publish_done(str(tmp_path))
    assert pipeline_debug_active(S()) is False


def test_first_post_debug_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUNTIME_OPERATIONAL_MODE", "first_post_debug")
    assert is_first_post_debug_mode() is True


def test_ai_gating_snapshot_keys() -> None:
    snap = ai_gating_snapshot()
    assert "ai_enabled" in snap
    assert "ai_block_reason" in snap
    assert "circuit_state" in snap
    assert "fallback_mode_active" in snap


def test_operational_mode_includes_first_post_debug() -> None:
    assert OperationalMode.FIRST_POST_DEBUG.value == "first_post_debug"
