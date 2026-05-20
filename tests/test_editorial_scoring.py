from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from sqlalchemy import select

from db.models import Draft, EditorialScore, RawPost
from db.session import init_db, session_scope
from editorial.scoring.base import SCORING_VERSION, PRIORITY_HIGH_THRESHOLD, publish_priority_label
from editorial.scoring.explainability import REASON_CATALOG, build_explainability
from editorial.scoring.operator_feedback import apply_operator_feedback
from editorial.scoring.metrics import (
    SCORED_ARTICLES_TOTAL,
    SCORING_FAILURES_TOTAL,
    reset_scoring_metrics_for_tests,
)
from editorial.scoring.models import EditorialIntelligenceScores, ScoringInput
from editorial.scoring.preview import render_editorial_intelligence_html
from editorial.scoring.service import compute_editorial_intelligence, enrich_draft_editorial_intelligence
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot, reset_metrics


def _raw_post(channel: str = "@src") -> RawPost:
    now = datetime.now(timezone.utc)
    return RawPost(
        id=1,
        channel_name=channel,
        message_id=1,
        text="Sample post text for scoring tests.",
        created_at=now,
        collected_at=now,
        processed_at=None,
    )


def _scoring_input(**overrides: object) -> ScoringInput:
    base = ScoringInput(
        draft_id=1,
        draft_text="Neutral report with two sources and moderate length for heuristics.",
        cluster_size=5,
        source_count=2,
        unique_channel_count=2,
        quality_scores={
            "coherence": 0.9,
            "length_quality": 0.85,
            "source_coverage": 0.8,
            "factual_confidence_heuristic": 0.75,
            "repetition": 0.1,
        },
        duplicate_intel={"max_similarity_pct": 12.0, "related": []},
        editorial_scores_card={"duplicate_confidence": 0.2},
        publication_priority={"publication_priority_score": 0.78},
        editorial_priority={"priority_level": "high", "numeric_priority_score": 72},
        source_trust_by_channel={"@src": 0.82, "@other": 0.76},
        source_convergence=0.6,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_compute_editorial_intelligence_deterministic() -> None:
    inp = _scoring_input()
    a = compute_editorial_intelligence(inp)
    b = compute_editorial_intelligence(inp)
    assert a.quality_score == b.quality_score
    assert a.novelty_score == b.novelty_score
    assert a.publish_priority_label == b.publish_priority_label
    assert 0.0 <= a.quality_score <= 1.0


def test_explainability_reason_codes_and_labels() -> None:
    inp = _scoring_input()
    scores = compute_editorial_intelligence(inp)
    assert scores.reason_codes
    assert "multi_source_confirmation" in scores.reason_codes
    assert scores.reasons
    assert REASON_CATALOG["multi_source_confirmation"] in scores.reasons


def test_scores_normalized_to_unit_interval() -> None:
    inp = _scoring_input()
    scores = compute_editorial_intelligence(inp)
    for attr in (
        "quality_score",
        "novelty_score",
        "source_trust_score",
        "duplicate_confidence",
        "cluster_importance_score",
        "publish_priority_score",
    ):
        v = getattr(scores, attr)
        assert 0.0 <= v <= 1.0


def test_priority_label_from_thresholds() -> None:
    assert publish_priority_label(PRIORITY_HIGH_THRESHOLD) == "HIGH"
    assert publish_priority_label(0.5) == "MEDIUM"
    assert publish_priority_label(0.1) == "LOW"


def test_scoring_version_present() -> None:
    scores = compute_editorial_intelligence(_scoring_input())
    assert scores.scoring_version == SCORING_VERSION
    assert scores.to_extras_payload()["scoring_version"] == SCORING_VERSION


def test_operator_feedback_hook() -> None:
    base = compute_editorial_intelligence(_scoring_input())
    updated = apply_operator_feedback(base, operator_feedback_score=0.9, operator_feedback_label="approve")
    assert updated.operator_feedback_score == pytest.approx(0.9)
    assert updated.operator_feedback_label == "approve"


def test_preview_html_includes_scores_and_reasons() -> None:
    scores = compute_editorial_intelligence(_scoring_input())
    html = render_editorial_intelligence_html(scores.to_extras_payload())
    assert "Editorial intelligence" in html
    assert "Why selected" in html
    assert "Quality:" in html


def test_fail_open_on_timeout() -> None:
    reset_metrics()
    reset_scoring_metrics_for_tests()
    settings = minimal_test_settings()

    async def _run() -> None:
        await init_db(settings.database_url)
        async with session_scope() as session:
            draft = Draft(
                content="x",
                content_hash="abc",
                sources="[]",
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
            session.add(draft)
            await session.flush()
            with patch(
                "editorial.scoring.service.asyncio.wait_for",
                side_effect=asyncio.TimeoutError(),
            ):
                out = await enrich_draft_editorial_intelligence(
                    session,
                    draft_id=int(draft.id),
                    draft_text="body",
                    used_posts=[_raw_post()],
                    cluster_size=3,
                    sources_payload=[{"channel": "@src", "message_id": 1}],
                    quality_scores={"coherence": 0.5},
                    duplicate_intel={},
                    editorial_scores_card={},
                    publication_priority=None,
                    editorial_priority=None,
                    runtime_dir=settings.runtime_state_dir,
                    timeout_sec=0.01,
                )
            assert out is None
            row = await session.scalar(
                select(EditorialScore).where(EditorialScore.draft_id == int(draft.id))
            )
            assert row is None

    asyncio.run(_run())
    ctr = export_snapshot()["counters"]
    assert ctr.get(SCORED_ARTICLES_TOTAL, 0) == 0
    assert ctr.get(SCORING_FAILURES_TOTAL, 0) >= 1


def test_db_persistence_roundtrip() -> None:
    reset_metrics()
    reset_scoring_metrics_for_tests()
    settings = minimal_test_settings()

    async def _run() -> None:
        await init_db(settings.database_url)
        async with session_scope() as session:
            draft = Draft(
                content="Persist scoring",
                content_hash="hash1",
                sources='[{"channel":"@a"}]',
                status="pending",
                created_at=datetime.now(timezone.utc),
            )
            session.add(draft)
            await session.flush()
            payload = await enrich_draft_editorial_intelligence(
                session,
                draft_id=int(draft.id),
                draft_text="Persist scoring with enough words for heuristics.",
                used_posts=[_raw_post("@a"), _raw_post("@b")],
                cluster_size=4,
                sources_payload=[
                    {"channel": "@a", "message_id": 1},
                    {"channel": "@b", "message_id": 2},
                ],
                quality_scores={
                    "coherence": 0.88,
                    "length_quality": 0.9,
                    "source_coverage": 0.7,
                    "factual_confidence_heuristic": 0.8,
                    "repetition": 0.05,
                },
                duplicate_intel={"max_similarity_pct": 5.0, "related": []},
                editorial_scores_card={"duplicate_confidence": 0.1},
                publication_priority={"publication_priority_score": 0.8},
                editorial_priority={"priority_level": "high"},
                runtime_dir=settings.runtime_state_dir,
                timeout_sec=2.0,
            )
            assert payload is not None
            assert payload.get("reason_codes")
            assert payload.get("reason_codes")
            assert payload.get("reasons")
            assert payload.get("scoring_version") == SCORING_VERSION
            assert payload.get("scoring_version") == SCORING_VERSION

            from db.editorial_scores_repository import get_editorial_scores_for_draft

            loaded = await get_editorial_scores_for_draft(session, int(draft.id))
            assert loaded is not None
            assert loaded["quality_score"] == pytest.approx(float(payload["quality_score"]), rel=1e-3)

    asyncio.run(_run())
    assert export_snapshot()["counters"].get(SCORED_ARTICLES_TOTAL, 0) >= 1
