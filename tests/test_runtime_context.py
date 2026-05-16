from __future__ import annotations

from unittest.mock import MagicMock

from scheduler.runtime_context import PipelineContext, get_pipeline_context, set_pipeline_context
from tests.conftest import minimal_test_settings


def test_pipeline_context_fields():
    settings = minimal_test_settings()
    bot = MagicMock(name="bot")
    openai = MagicMock(name="openai")
    ctx = PipelineContext(settings=settings, bot=bot, openai=openai)

    assert ctx.settings is settings
    assert ctx.bot is bot
    assert ctx.openai is openai
    assert ctx.tick_timings == {}
    assert ctx.tick_in_progress is False
    assert ctx.last_cluster_size == 0


def test_get_set_clear_context_no_scheduler():
    settings = minimal_test_settings()
    ctx = PipelineContext(settings=settings, bot=MagicMock(), openai=MagicMock())

    assert get_pipeline_context() is None
    set_pipeline_context(ctx)
    assert get_pipeline_context() is ctx
    set_pipeline_context(None)
    assert get_pipeline_context() is None


def test_context_lazy_dict_mutation_is_local():
    settings = minimal_test_settings()
    ctx = PipelineContext(settings=settings, bot=MagicMock(), openai=MagicMock())
    ctx.tick_timings["collect_sec"] = 1.23
    assert ctx.tick_timings["collect_sec"] == 1.23

    ctx2 = PipelineContext(settings=settings, bot=MagicMock(), openai=MagicMock())
    assert "collect_sec" not in ctx2.tick_timings
