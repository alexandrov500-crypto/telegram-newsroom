from __future__ import annotations

import asyncio
from pathlib import Path

from bot.live_deploy.first_72h import First72HMode
from bot.live_deploy.publication_guard import LivePublicationGuard
from bot.live_deploy.repository import LiveDeployRepository
from bot.live_deploy.settings import LiveDeploySettings
from bot.storage.db import init_database


def test_first_72h_thresholds(tmp_path: Path) -> None:
    init_database(tmp_path / "ld.db")
    repo = LiveDeployRepository(tmp_path / "ld.db")
    settings = LiveDeploySettings(first_72h_mode=True, first_72h_hours=72)
    repo.init_state(production_start_at="2026-05-17T00:00:00+00:00")
    mode = First72HMode(settings, repo)
    assert mode.active()
    t = mode.thresholds()
    assert t["min_quality"] >= 0.78
    assert t["mandatory_approval"] is True


def test_publication_guard_blocks(tmp_path: Path) -> None:
    init_database(tmp_path / "ld2.db")
    repo = LiveDeployRepository(tmp_path / "ld2.db")
    settings = LiveDeploySettings(first_72h_mode=True)
    repo.init_state(production_start_at="2026-05-17T00:00:00+00:00")
    guard = LivePublicationGuard(repo, First72HMode(settings, repo))
    v = guard.evaluate(
        pending_news_id=1,
        quality_score=0.5,
        trust_score=0.5,
        publish_confidence=0.5,
        operator_approved=False,
        signals={"war_room_active": True},
    )
    assert not v.allowed
    assert v.route_shadow


def test_prelaunch_checklist(tmp_path: Path) -> None:
    from bot.live_deploy.coordinator import LiveDeployCoordinator
    from bot.live_deploy.executive_report import ExecutiveGoLiveReport

    coord = LiveDeployCoordinator(
        settings=LiveDeploySettings(),
        repository=LiveDeployRepository(tmp_path / "ld3.db"),
        first_72h=First72HMode(LiveDeploySettings(), LiveDeployRepository(tmp_path / "ld3.db")),
        publication_guard=LivePublicationGuard(
            LiveDeployRepository(tmp_path / "ld3.db"),
            First72HMode(LiveDeploySettings(), LiveDeployRepository(tmp_path / "ld3.db")),
        ),
        executive=ExecutiveGoLiveReport(LiveDeployRepository(tmp_path / "ld3.db")),
    )
    ok, failed = coord.prelaunch_checklist(
        {
            "env_valid": True,
            "telegram_permissions": True,
            "redis_healthy": True,
            "postgres_healthy": True,
            "openai_configured": True,
            "rollout_safe": True,
            "ga_readiness": True,
            "rc1_lockdown": True,
            "operator_allowlist": True,
            "rollback_snapshot": True,
            "certification": True,
        },
    )
    assert ok and not failed


def test_coordinator_tick(tmp_path: Path) -> None:
    async def _run() -> None:
        from bot.live_deploy.factory import build_live_deploy_stack

        init_database(tmp_path / "ld4.db")
        coord = build_live_deploy_stack(tmp_path / "ld4.db")
        await coord.startup()
        t = await coord.tick({"quality_avg": 0.9})
        assert "first_72h_active" in t

    asyncio.run(_run())
