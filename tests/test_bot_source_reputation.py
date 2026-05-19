from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.processing import priority as pr
from bot.processing.source_reliability import clamp_trust, normalize_source_name
from bot.storage.db import init_database
from bot.storage.source_repository import SourceRepository


@pytest.fixture
def source_repo(tmp_path: Path) -> SourceRepository:
    db_path = init_database(tmp_path / "sources.db")
    return SourceRepository(db_path)


def test_approvals_increase_trust(source_repo: SourceRepository) -> None:
    profile = source_repo.touch_source("telegram:@reuters")
    start = profile.trust_score
    source_repo.record_approval("telegram:@reuters")
    source_repo.record_approval("telegram:@reuters")
    updated = source_repo.get_source("telegram:@reuters")
    assert updated is not None
    assert updated.trust_score > start
    assert updated.trust_score <= 0.99
    assert updated.accepted_count >= 2


def test_rejections_decrease_trust(source_repo: SourceRepository) -> None:
    profile = source_repo.touch_source("telegram:@spamfeed")
    start = profile.trust_score
    source_repo.record_rejection("telegram:@spamfeed")
    source_repo.record_rejection("telegram:@spamfeed")
    updated = source_repo.get_source("telegram:@spamfeed")
    assert updated is not None
    assert updated.trust_score < start
    assert updated.trust_score >= 0.05
    assert updated.rejected_count >= 2


def test_trust_affects_priority() -> None:
    async def run() -> tuple[float, float]:
        high = await pr.calculate_priority(
            title="SEC approves ETF",
            summary="Regulators updated guidance.",
            tags=["regulation"],
            source_trust=0.9,
            source_approval_ratio=0.9,
        )
        low = await pr.calculate_priority(
            title="SEC approves ETF",
            summary="Regulators updated guidance.",
            tags=["regulation"],
            source_trust=0.15,
            source_approval_ratio=0.1,
        )
        return float(high["score"]), float(low["score"])

    high_score, low_score = asyncio.run(run())
    assert high_score > low_score


def test_unknown_source_fallback(source_repo: SourceRepository) -> None:
    profile = source_repo.get_profile(None)
    assert profile.trust_score == pytest.approx(0.5, abs=0.01)
    assert profile.source_name == "unknown"


def test_malformed_source_name_safe(source_repo: SourceRepository) -> None:
    name = normalize_source_name("  https://www.Reuters.com/path?q=1  ")
    assert name == "reuters.com"
    profile = source_repo.touch_source(name)
    assert profile.source_name == "reuters.com"
    assert profile.trust_score >= 0.05


def test_trust_clamped() -> None:
    assert clamp_trust(0.0) == 0.05
    assert clamp_trust(1.5) == 0.99


def test_persistence_after_restart(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "sources_restart.db")
    repo = SourceRepository(db_path)
    repo.touch_source("feeds.bbci.co.uk")
    repo.record_approval("feeds.bbci.co.uk")

    reloaded = SourceRepository(db_path)
    profile = reloaded.get_source("feeds.bbci.co.uk")
    assert profile is not None
    assert profile.accepted_count >= 1
