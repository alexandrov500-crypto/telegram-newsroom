from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.platform.cognition.agents import MultiAgentCognitionOrchestrator
from bot.platform.factory import build_platform_stack
from bot.platform.graph.store import OperationalKnowledgeGraph
from bot.platform.plugins.registry import PluginRegistry
from bot.platform.policy.engine import PolicyEngine
from bot.platform.repository import PlatformRepository
from bot.platform.sdk.helpers import invoke_internal, policy_simulate
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "platform.db"
    init_database(p)
    return p


@pytest.fixture
def repo(db_path: Path) -> PlatformRepository:
    return PlatformRepository(db_path)


def test_plugin_registry_bootstrap(repo: PlatformRepository) -> None:
    reg = PluginRegistry(repo)
    reg.bootstrap()
    plugins = reg.list_live()
    assert len(plugins) >= 3
    assert any(p["plugin_id"] == "core.rss_ingest" for p in plugins)


def test_policy_simulate(repo: PlatformRepository) -> None:
    engine = PolicyEngine(repo)
    engine.bootstrap_defaults()
    r = engine.simulate("publish", {"quality_score": 0.9})
    assert r["allowed"] is True
    r2 = engine.simulate("publish", {"quality_score": 0.5})
    assert r2["allowed"] is False


def test_graph_edges(repo: PlatformRepository) -> None:
    g = OperationalKnowledgeGraph(repo)
    g.story_source(42, "rss:bbc")
    g.risk_incident("latency", "inc-1")
    neighbors = repo.graph_neighbors("story", "42")
    assert len(neighbors) >= 1


def test_multi_agent_debate() -> None:
    orch = MultiAgentCognitionOrchestrator()
    d = orch.run_debate(7, source_trust=0.9, contradiction=0.05)
    assert d.consensus > 0.7
    trace = orch.debate_trace_text(7)
    assert "trust_agent" in trace


def test_platform_coordinator_tick(db_path: Path) -> None:
    async def _run() -> None:
        coord = build_platform_stack(db_path)
        await coord.startup()
        tick = await coord.tick(signals={"failure_issues": [{"id": "x1"}]})
        assert tick["plugins"] >= 3
        assert "ecosystem_risk" in tick

    asyncio.run(_run())


def test_internal_gateway(repo: PlatformRepository) -> None:
    from bot.platform.context_holder import install_platform

    async def _run() -> None:
        coord = build_platform_stack(repo._db_path)
        await coord.startup()
        install_platform(coord)
        r = await invoke_internal("health", scope="read")
        assert r["ok"] is True

    asyncio.run(_run())


def test_policy_sdk_offline() -> None:
    from bot.platform.context_holder import install_platform

    install_platform(None)
    assert policy_simulate("publish", {})["allowed"] is False
