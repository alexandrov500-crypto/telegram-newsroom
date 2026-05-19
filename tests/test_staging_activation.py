from __future__ import annotations

from pathlib import Path

import pytest

from bot.staging.feeds_config import load_staging_feed_catalog, resolve_staging_feed_urls
from bot.staging.safety import StagingSafetyEnforcer
from bot.staging.shadow_publish import StagingPublishGuard
from bot.storage.db import init_database


def test_staging_feed_catalog_loads() -> None:
    root = Path(__file__).resolve().parent.parent
    cat = load_staging_feed_catalog(root / "config" / "feeds.staging.yaml")
    assert "reuters_world" in cat
    assert "noisy_bbc_all" in cat
    urls = resolve_staging_feed_urls(
        catalog_path=root / "config" / "feeds.staging.yaml",
        env_feeds=("https://example.com/extra.rss",),
    )
    assert len(urls) >= 5
    assert "https://example.com/extra.rss" in urls


def test_shadow_publish_blocks_production_channel() -> None:
    guard = StagingPublishGuard(
        staging_mode=True,
        shadow_only=True,
        blocked_channel_ids=frozenset([-1009999999999]),
        repository=None,
    )
    verdict = guard.evaluate_channel(-1009999999999)
    assert not verdict.allowed
    assert verdict.reason == "production_channel_blocked"


def test_staging_safety_requires_operator() -> None:
    enforcer = StagingSafetyEnforcer()
    v = enforcer.evaluate(
        auto_approval=False,
        publish_confidence=0.9,
        operator_approved=False,
        staging_mode=True,
    )
    assert not v.allowed
    v2 = enforcer.evaluate(
        auto_approval=False,
        publish_confidence=0.9,
        operator_approved=True,
        staging_mode=True,
    )
    assert v2.allowed


def test_staging_safety_misinfo_gate() -> None:
    enforcer = StagingSafetyEnforcer()
    v = enforcer.evaluate(
        auto_approval=False,
        publish_confidence=0.5,
        misinfo_score=0.9,
        operator_approved=False,
        staging_mode=False,
    )
    assert not v.allowed
    assert v.blocked_reason == "misinformation_gate"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "staging.db")
