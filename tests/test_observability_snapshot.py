from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from scheduler.jobs import build_pipeline_context
from scheduler.runtime_context import set_pipeline_context
from tests.conftest import minimal_test_settings
from utils.metrics import inc, reset_metrics
from utils.observability import get_runtime_snapshot


@pytest.fixture(autouse=True)
def clear_pipeline_context():
    set_pipeline_context(None)
    yield
    set_pipeline_context(None)


def test_runtime_snapshot_schema_json_serializable_no_scheduler_loop():
    reset_metrics()
    set_pipeline_context(None)
    inc("posts_collected", 7)
    settings = minimal_test_settings()
    snap = get_runtime_snapshot(settings)
    assert snap["schema_version"] == 1
    assert "uptime_sec" in snap
    assert "asyncio_tasks" in snap
    assert "metrics" in snap
    assert "scheduler" in snap
    assert "tick_timings_last" in snap
    assert snap["posts_collected_total"] == 7
    assert snap.get("drafts_created_total", 0) == 0
    assert snap.get("drafts_published_total", 0) == 0
    assert snap["scheduler"] == {}
    assert "tick_timing_statistics" in snap
    assert "recent_runtime_events" in snap
    assert "editorial_intelligence" in snap
    assert "breaking_runtime_events_recent" in snap["editorial_intelligence"]
    json.dumps(snap, default=str)


def test_runtime_snapshot_with_pipeline_context():
    reset_metrics()
    settings = minimal_test_settings()
    bot = MagicMock()
    bot.session = MagicMock()
    bot.session.close = AsyncMock()
    openai = MagicMock()
    openai.close = AsyncMock()
    ctx = build_pipeline_context(settings, bot, openai)
    ctx.tick_timings["collect_sec"] = 0.1
    ctx.tick_in_progress = False
    ctx.last_cluster_size = 3
    ctx.last_scheduler_wall_sec = 1.25
    ctx.duplicate_skipped_this_tick = False

    snap = get_runtime_snapshot(settings)
    assert snap["scheduler"]["last_cluster_size"] == 3
    assert snap["tick_timings_last"]["collect_sec"] == 0.1
    json.dumps(snap, default=str)
