from __future__ import annotations

import asyncio
from pathlib import Path

from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode
from bot.live_ops.controlled_factory import build_controlled_live_stack
from bot.live_ops.publish_guard import LiveChannelPublishGuard
from bot.live_ops.repository import LiveChannelRepository
from bot.storage.db import init_database


def test_publish_guard_blocks_empty(tmp_path: Path) -> None:
    init_database(tmp_path / "cl1.db")
    repo = LiveChannelRepository(tmp_path / "cl1.db")
    repo.ensure_state(live_mode=LiveMode.SUPERVISED_LIVE.value)
    coord = build_controlled_live_stack(tmp_path / "cl1.db")
    coord.repository.ensure_state(live_mode=LiveMode.SUPERVISED_LIVE.value)
    v = coord.publish_guard.evaluate(
        pending_news_id=1,
        headline="Hi",
        summary="",
        source="reuters",
        topic="news",
        operator_approved=True,
        quality_score=0.9,
        trust_score=0.9,
    )
    assert not v.allowed
    assert any("empty" in b or "short" in b for b in v.blockers)


def test_shadow_mode_routes_shadow(tmp_path: Path) -> None:
    init_database(tmp_path / "cl2.db")
    repo = LiveChannelRepository(tmp_path / "cl2.db")
    repo.ensure_state(live_mode=LiveMode.SHADOW.value)
    coord = build_controlled_live_stack(tmp_path / "cl2.db")
    v = coord.publish_guard.evaluate(
        pending_news_id=2,
        headline="Valid headline for shadow",
        summary="A sufficiently long summary body for shadow routing validation.",
        source="reuters",
        topic="news",
        operator_approved=False,
        quality_score=0.9,
        trust_score=0.9,
    )
    assert v.allowed
    assert v.route_shadow


def test_pause_and_freeze(tmp_path: Path) -> None:
    init_database(tmp_path / "cl3.db")
    coord = build_controlled_live_stack(tmp_path / "cl3.db")
    coord.repository.ensure_state()
    coord.override.pause_live()
    state = coord.repository.get_state()
    assert state["paused"] == 1
    coord.freeze.freeze_publishing()
    state = coord.repository.get_state()
    assert state["frozen"] == 1


def test_rollback_sets_shadow(tmp_path: Path) -> None:
    from bot.runtime.state import runtime_state

    init_database(tmp_path / "cl4.db")
    coord = build_controlled_live_stack(tmp_path / "cl4.db")
    runtime_state.shadow_publish_only = False
    result = coord.rollback.rollback_last_batch()
    assert result["shadow"] is True
    assert runtime_state.shadow_publish_only is True


def test_coordinator_tick(tmp_path: Path) -> None:
    async def _run() -> None:
        init_database(tmp_path / "cl5.db")
        coord = build_controlled_live_stack(tmp_path / "cl5.db")
        await coord.startup()
        out = await coord.tick(signals={"engagement_quality": 0.8, "publish_fatigue": 0.2})
        assert "live_mode" in out

    asyncio.run(_run())


def test_mark_post_updates_scores(tmp_path: Path) -> None:
    init_database(tmp_path / "cl6.db")
    coord = build_controlled_live_stack(tmp_path / "cl6.db")
    coord.repository.ensure_state()
    coord.override.mark_post(pending_news_id=99, good=False)
    coord.feedback.update_derived_scores()
    state = coord.repository.get_state()
    assert state is not None
