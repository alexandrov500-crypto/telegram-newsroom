"""Terminal state resolver — deterministic tick outcomes."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.reliability.terminal_state_resolver import (
    apply_forced_reject_idle,
    resolve_terminal_state,
)
from scheduler.runtime_context import PipelineContext


@pytest.fixture
def pipeline_ctx() -> PipelineContext:
    return PipelineContext(settings=MagicMock(), bot=MagicMock(), openai=MagicMock())


def _ctx(base: PipelineContext, **kwargs) -> PipelineContext:
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


def test_committed_draft_when_draft_id_set(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx, tick_draft_id=42)
    res = resolve_terminal_state(ctx, raw_unprocessed=10)
    assert res.terminal_state == "committed_draft"
    assert res.tick_status == "ok"
    assert res.drafts_created == 1


def test_committed_reject_on_openai_idle(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx, tick_summarize_idle_reason="openai_failed:429 quota")
    res = resolve_terminal_state(ctx, raw_unprocessed=5)
    assert res.terminal_state == "committed_reject"
    assert res.tick_status == "reject"


def test_forced_reject_on_backlog_without_idle(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx)
    res = resolve_terminal_state(ctx, raw_unprocessed=3)
    assert res.terminal_state == "committed_reject"
    assert "backlog_without_terminal" in res.reason


def test_committed_idle_no_backlog(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx, tick_summarize_idle_reason="no_unprocessed_posts")
    res = resolve_terminal_state(ctx, raw_unprocessed=0)
    assert res.terminal_state == "committed_idle"
    assert res.tick_status == "ok"


def test_apply_forced_reject_idle_prefix(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx)
    apply_forced_reject_idle(ctx, "429 quota exceeded")
    assert ctx.tick_summarize_idle_reason.startswith("openai_failed:")


def test_detail_json_shape(pipeline_ctx: PipelineContext) -> None:
    ctx = _ctx(pipeline_ctx, tick_draft_id=7, tick_collect_rows=2)
    res = resolve_terminal_state(ctx, raw_unprocessed=0)
    detail = res.to_detail(ctx)
    assert detail["terminal_state"] == "committed_draft"
    assert detail["draft_id"] == 7
    assert detail["collect_rows"] == 2
