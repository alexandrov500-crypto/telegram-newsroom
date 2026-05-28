"""PipelineContext must expose tick_failures (slots dataclass — no dynamic attrs)."""

from __future__ import annotations

from scheduler.runtime_context import PipelineContext


def test_pipeline_context_has_tick_failures_slot() -> None:
    fields = {f.name for f in PipelineContext.__dataclass_fields__.values()}
    assert "tick_failures" in fields
