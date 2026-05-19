from __future__ import annotations

from pathlib import Path

import pytest

from bot.processing import semantic as sm
from bot.storage.cluster_repository import ClusterAttachOutcome, ClusterRepository
from bot.storage.db import init_database
from bot.storage.editorial_repository import EditorialRepository


@pytest.fixture
def db_bundle(tmp_path: Path) -> tuple[ClusterRepository, EditorialRepository, Path]:
    db_path = init_database(tmp_path / "semantic_cluster.db")
    clusters = ClusterRepository(db_path, similarity_threshold=0.72)
    editorial = EditorialRepository(db_path)
    return clusters, editorial, db_path


def test_same_story_titles_have_high_jaccard() -> None:
    left, _ = sm.build_fingerprint("SEC approves Bitcoin ETF")
    right, _ = sm.build_fingerprint("Bitcoin ETF approved by SEC")
    score = sm.jaccard_similarity(left, right)
    assert score >= 0.72


def test_different_stories_have_low_jaccard() -> None:
    left, _ = sm.build_fingerprint("SEC approves Bitcoin ETF")
    right, _ = sm.build_fingerprint("Mars rover discovers underground ice cave")
    score = sm.jaccard_similarity(left, right)
    assert score < 0.72


def test_second_variant_matches_without_enqueue(db_bundle) -> None:
    clusters, editorial, _ = db_bundle
    first = clusters.attach_story_variant(
        title="SEC approves Bitcoin ETF",
        summary="Regulators cleared a new spot Bitcoin ETF framework.",
        link="https://reuters.com/bitcoin-etf",
        source="Reuters",
    )
    assert first.outcome == ClusterAttachOutcome.NEW_CLUSTER
    assert first.should_enqueue is True

    pending_id = editorial.enqueue_news(
        title="SEC approves Bitcoin ETF",
        summary="Regulators cleared a new spot Bitcoin ETF framework.",
        link="https://reuters.com/bitcoin-etf",
        tags=["crypto", "etf"],
        source="Reuters",
        cluster_id=first.cluster_id,
    )
    assert pending_id == 1

    second = clusters.attach_story_variant(
        title="Bitcoin ETF approved by SEC",
        summary="US regulators approved spot Bitcoin ETFs.",
        link="https://bloomberg.com/bitcoin-etf",
        source="Bloomberg",
    )
    assert second.outcome == ClusterAttachOutcome.MATCHED
    assert second.should_enqueue is False
    assert second.similarity is not None
    assert second.similarity >= 0.72

    pending = editorial.get_pending_news(limit=10)
    assert len(pending) == 1
    view = clusters.get_cluster_view(first.cluster_id)
    assert view.variant_count == 2
    assert "Reuters" in view.sources
    assert "Bloomberg" in view.sources


def test_different_stories_create_separate_clusters(db_bundle) -> None:
    clusters, editorial, _ = db_bundle
    a = clusters.attach_story_variant(
        title="SEC approves Bitcoin ETF",
        summary="ETF news",
        link="https://a.com/1",
        source="Reuters",
    )
    b = clusters.attach_story_variant(
        title="Mars rover discovers underground ice cave",
        summary="Space news",
        link="https://b.com/2",
        source="NASA",
    )
    assert a.cluster_id != b.cluster_id
    assert a.should_enqueue and b.should_enqueue


def test_clusters_persist_after_restart(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "semantic_restart.db")
    clusters = ClusterRepository(db_path, similarity_threshold=0.72)
    clusters.attach_story_variant(
        title="SEC approves Bitcoin ETF",
        summary="ETF news",
        link="https://reuters.com/1",
        source="Reuters",
    )

    clusters_reloaded = ClusterRepository(db_path, similarity_threshold=0.72)
    matched = clusters_reloaded.attach_story_variant(
        title="Bitcoin ETF approved by SEC",
        summary="ETF news variant",
        link="https://coindesk.com/2",
        source="CoinDesk",
    )
    assert matched.outcome == ClusterAttachOutcome.MATCHED
    view = clusters_reloaded.get_cluster_view(matched.cluster_id)
    assert view.variant_count == 2
