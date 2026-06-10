from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.growth_layer.validation.acquisition_proxy import (
    acquisition_proxy_score,
    compute_acquisition_components,
)
from app.growth_layer.validation.backfill import _build_actuals_from_snapshot, _validation_status_for_snapshot
from app.growth_layer.validation.calibration import (
    build_tier_confusion_matrix,
    build_virality_calibration,
    predicted_tier_label,
)
from app.growth_layer.validation.decision import evaluate_format_decision
from app.growth_layer.validation.rankings import build_growth_rankings
from app.growth_layer.validation.status import ValidationStatus, is_final_row
from app.growth_layer.validation.weekly_report import build_weekly_growth_report
from db.models import PostPerformance


def _row(
    *,
    draft_id: int,
    fmt: str,
    predicted: int,
    engagement: float,
    forwards: int,
    err: float,
    forward_rate: float | None = None,
    topic: str = "macro",
    source: str = "@cb_economics",
    tier: str = "enhanced",
    status: str = "FINAL",
    virality_score: float = 0.5,
) -> dict:
    components = compute_acquisition_components(forwards=float(forwards), err=err, engagement=engagement)
    return {
        "draft_id": draft_id,
        "format_profile": fmt,
        "predicted_virality": predicted,
        "virality_tier": tier,
        "validation_status": status,
        "snapshot_label": "t24h" if status == "FINAL" else "t6h",
        "actual_engagement": engagement,
        "actual_forwards": forwards,
        "actual_views": max(forwards * 50, 100),
        "actual_err": err,
        "actual_forward_rate": forward_rate if forward_rate is not None else forwards / max(forwards * 50, 100),
        "actual_virality_score": virality_score,
        **components,
        "topic_bucket": topic,
        "primary_source": source,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def test_calibration_correlation_and_mae() -> None:
    rows = [
        _row(draft_id=1, fmt="cb_brief", predicted=30, engagement=0.25, forwards=2, err=0.4, tier="standard"),
        _row(draft_id=2, fmt="cb_brief", predicted=50, engagement=0.45, forwards=5, err=0.55, tier="enhanced"),
        _row(draft_id=3, fmt="growth_brief", predicted=80, engagement=0.72, forwards=12, err=0.8, tier="viral_candidate"),
        _row(draft_id=4, fmt="growth_brief", predicted=90, engagement=0.78, forwards=15, err=0.85, tier="viral_candidate"),
    ]
    report = build_virality_calibration(rows)
    assert report.sample_size == 4
    assert report.correlation is not None
    assert report.correlation > 0.8
    assert report.mae is not None
    assert report.mae < 0.2


def test_calibration_ignores_non_final_rows() -> None:
    rows = [
        _row(draft_id=1, fmt="cb_brief", predicted=50, engagement=0.4, forwards=4, err=0.5, status="T6_READY"),
        _row(draft_id=2, fmt="cb_brief", predicted=50, engagement=0.5, forwards=5, err=0.55, status="FINAL"),
    ]
    report = build_virality_calibration(rows)
    assert report.sample_size == 1


def test_tier_confusion_matrix() -> None:
    rows = [
        _row(draft_id=1, fmt="cb_brief", predicted=80, engagement=0.7, forwards=10, err=0.7, tier="viral_candidate", virality_score=0.75),
        _row(draft_id=2, fmt="cb_brief", predicted=80, engagement=0.3, forwards=2, err=0.3, tier="viral_candidate", virality_score=0.25),
        _row(draft_id=3, fmt="cb_brief", predicted=50, engagement=0.5, forwards=5, err=0.5, tier="enhanced", virality_score=0.5),
    ]
    matrix = build_tier_confusion_matrix(rows)
    assert matrix["high"]["high"] >= 1
    assert sum(matrix["high"].values()) >= 2


def test_predicted_tier_label_mapping() -> None:
    assert predicted_tier_label({"virality_tier": "viral_candidate"}) == "high"
    assert predicted_tier_label({"virality_tier": "enhanced"}) == "medium"
    assert predicted_tier_label({"virality_tier": "standard"}) == "low"


def test_decision_recommends_growth_brief_when_lift_met() -> None:
    rows = []
    rng = __import__("random").Random(99)
    for i in range(30):
        rows.append(
            _row(
                draft_id=i,
                fmt="cb_brief",
                predicted=40,
                engagement=0.35 + rng.uniform(-0.02, 0.02),
                forwards=3,
                err=0.50 + rng.uniform(-0.02, 0.02),
                forward_rate=0.020 + rng.uniform(-0.001, 0.001),
            )
        )
    for i in range(30, 55):
        rows.append(
            _row(
                draft_id=i,
                fmt="growth_brief",
                predicted=85,
                engagement=0.55 + rng.uniform(-0.02, 0.02),
                forwards=8,
                err=0.62 + rng.uniform(-0.02, 0.02),
                forward_rate=0.028 + rng.uniform(-0.001, 0.001),
                tier="viral_candidate",
            )
        )
    verdict = evaluate_format_decision(rows)
    assert verdict.meets_threshold is True
    assert verdict.statistically_significant is True
    assert verdict.recommended_mode == "growth_brief"
    assert verdict.confidence == "LOW"
    assert verdict.sample_size == 55
    assert verdict.err_lift_pct is not None and verdict.err_lift_pct >= 10.0
    assert verdict.forward_lift_pct is not None and verdict.forward_lift_pct >= 15.0
    assert verdict.err_p_value is not None and verdict.err_p_value < 0.05


def test_decision_confidence_levels() -> None:
    rows = [
        _row(draft_id=i, fmt="cb_brief", predicted=50, engagement=0.4, forwards=4, err=0.5)
        for i in range(120)
    ]
    verdict = evaluate_format_decision(rows)
    assert verdict.confidence == "MEDIUM"
    assert verdict.sample_size == 120


def test_decision_guardrails_insufficient_control_group() -> None:
    rows = []
    for i in range(5):
        rows.append(_row(draft_id=i, fmt="cb_brief", predicted=40, engagement=0.35, forwards=3, err=0.5))
    for i in range(5, 55):
        rows.append(
            _row(
                draft_id=i,
                fmt="growth_brief",
                predicted=85,
                engagement=0.55,
                forwards=8,
                err=0.62,
                forward_rate=0.028,
            )
        )
    verdict = evaluate_format_decision(rows)
    assert verdict.recommended_mode == "hybrid"
    assert verdict.reason == "insufficient_control_group"


def test_decision_stays_hybrid_on_small_sample() -> None:
    rows = [_row(draft_id=i, fmt="cb_brief", predicted=50, engagement=0.4, forwards=4, err=0.5) for i in range(10)]
    verdict = evaluate_format_decision(rows)
    assert verdict.recommended_mode == "hybrid"
    assert verdict.meets_threshold is False


def test_acquisition_components_storage_and_recompute() -> None:
    components = compute_acquisition_components(forwards=10.0, err=0.6, engagement=0.5)
    assert components["forward_component"] == 20.0
    assert components["err_component"] == 30.0
    assert components["engagement_component"] == 5.0
    assert components["acquisition_proxy_score"] == 55.0
    row = {"forward_component": 20.0, "err_component": 30.0, "engagement_component": 5.0}
    assert acquisition_proxy_score(row) == 55.0


def test_acquisition_legacy_fallback() -> None:
    row = {"actual_forwards": 10, "actual_err": 0.6, "actual_engagement": 0.5}
    assert acquisition_proxy_score(row) == 55.0


def test_rankings_use_acquisition_components() -> None:
    rows = [
        _row(draft_id=1, fmt="cb_brief", predicted=40, engagement=0.3, forwards=2, err=0.4),
        _row(draft_id=2, fmt="growth_brief", predicted=80, engagement=0.6, forwards=20, err=0.9),
    ]
    rankings = build_growth_rankings(rows)
    assert rankings.top_subscriber_drivers[0]["draft_id"] == 2
    assert "forward_component" in rankings.top_subscriber_drivers[0]


def test_validation_status_transitions() -> None:
    assert _validation_status_for_snapshot("t6h") == ValidationStatus.T6_READY.value
    assert _validation_status_for_snapshot("t24h") == ValidationStatus.FINAL.value
    assert is_final_row({"validation_status": "FINAL"})
    assert not is_final_row({"validation_status": "T6_READY", "actual_engagement": 0.5})


def test_build_actuals_from_snapshot_includes_components() -> None:
    snap = PostPerformance(
        draft_id=1,
        telegram_post_id=1,
        channel_id=1,
        published_at=datetime.now(timezone.utc),
        snapshot_label="t24h",
        snapshot_at=datetime.now(timezone.utc),
        views=500,
        forwards=12,
        reactions_total=8,
        subscribers_at_snapshot=1000,
        engagement_score=0.55,
        virality_score=0.42,
    )
    actuals = _build_actuals_from_snapshot(snap)
    assert actuals["snapshot_label"] == "t24h"
    assert "forward_component" in actuals
    assert actuals["acquisition_proxy_score"] > 0


def test_weekly_report_contains_sections() -> None:
    rows = [_row(draft_id=1, fmt="cb_brief", predicted=50, engagement=0.4, forwards=5, err=0.55)]
    html = build_weekly_growth_report(week_rows=rows, all_rows=rows, audience_delta_7d=42)
    assert "Weekly Growth Report" in html
    assert "Growth Brief vs CB Brief" in html
    assert "STATISTICAL VALIDATION" in html
    assert "confidence" in html
    assert "Confusion" in html
    assert "Рекомендации для редакции" in html


def test_validation_repository_roundtrip() -> None:
    import asyncio

    async def _run() -> None:
        from app.growth_layer.validation.experiment import finalize_post_validation, record_publish_experiment
        from db.growth_validation_repository import list_post_growth_validation
        from db.models import Draft, DraftStatus
        from db.repository import utcnow
        from db.session import init_db, session_scope

        await init_db("sqlite+aiosqlite:///:memory:")
        async with session_scope() as session:
            draft = Draft(
                content="test",
                content_hash="valhash",
                sources='[{"channel":"@cb_economics"}]',
                draft_extras=json.dumps(
                    {
                        "growth": {
                            "virality_score": 78,
                            "virality_tier": "viral_candidate",
                            "format_profile": "growth_brief",
                        }
                    }
                ),
                status=DraftStatus.PUBLISHED.value,
                created_at=utcnow(),
            )
            session.add(draft)
            await session.flush()
            await record_publish_experiment(
                session,
                draft_id=int(draft.id),
                telegram_post_id=999,
                published_at=utcnow(),
                extras_json=draft.draft_extras,
                topic_bucket="macro",
                primary_source="@cb_economics",
            )
            pending = await list_post_growth_validation(session, limit=10)
            assert pending[0]["validation_status"] == ValidationStatus.PENDING.value

            await finalize_post_validation(
                session,
                draft_id=int(draft.id),
                telegram_post_id=999,
                snapshot_label="t6h",
                views=300,
                forwards=6,
                reactions=4,
                subscribers=1000,
                engagement_score=0.45,
                virality_score=0.35,
                hours_since_publish=6.0,
            )
            t6 = await list_post_growth_validation(session, limit=10)
            assert t6[0]["validation_status"] == ValidationStatus.T6_READY.value

            await finalize_post_validation(
                session,
                draft_id=int(draft.id),
                telegram_post_id=999,
                snapshot_label="t24h",
                views=500,
                forwards=12,
                reactions=8,
                subscribers=1000,
                engagement_score=0.55,
                virality_score=0.42,
                hours_since_publish=24.0,
            )
            rows = await list_post_growth_validation(session, limit=10, final_only=True)
            assert len(rows) == 1
            assert rows[0]["format_profile"] == "growth_brief"
            assert rows[0]["predicted_virality"] == 78
            assert rows[0]["actual_forwards"] == 12
            assert rows[0]["actual_err"] == pytest.approx(0.5, rel=0.01)
            assert rows[0]["validation_status"] == ValidationStatus.FINAL.value
            assert rows[0]["forward_component"] == 24.0

    asyncio.run(_run())


def test_backfill_idempotent() -> None:
    import asyncio

    async def _run() -> None:
        from app.growth_layer.validation.backfill import backfill_growth_validation
        from db.models import Draft, DraftGrowthScore, DraftStatus, PostPerformance, PublishedPost
        from db.repository import utcnow
        from db.session import init_db, session_scope

        await init_db("sqlite+aiosqlite:///:memory:")
        now = utcnow()
        async with session_scope() as session:
            draft = Draft(
                content="backfill test",
                content_hash="bf1",
                sources='[{"channel":"@rbc_news"}]',
                draft_extras=json.dumps({"growth": {"virality_score": 65, "virality_tier": "enhanced", "format_profile": "cb_brief"}}),
                status=DraftStatus.PUBLISHED.value,
                created_at=now,
            )
            session.add(draft)
            await session.flush()
            session.add(
                PublishedPost(draft_id=int(draft.id), telegram_post_id=1001, published_at=now)
            )
            session.add(
                DraftGrowthScore(
                    draft_id=int(draft.id),
                    virality_score=65,
                    virality_tier="enhanced",
                    format_profile="cb_brief",
                    computed_at=now,
                )
            )
            session.add(
                PostPerformance(
                    draft_id=int(draft.id),
                    telegram_post_id=1001,
                    channel_id=1,
                    published_at=now,
                    snapshot_label="t24h",
                    snapshot_at=now,
                    views=400,
                    forwards=8,
                    reactions_total=5,
                    subscribers_at_snapshot=800,
                    engagement_score=0.48,
                    virality_score=0.38,
                    primary_source="@rbc_news",
                    topic_bucket="macro",
                )
            )
            await session.flush()

            stats1 = await backfill_growth_validation(session, dry_run=False)
            assert stats1.created == 1

            stats2 = await backfill_growth_validation(session, dry_run=False)
            assert stats2.created == 0
            assert stats2.skipped_existing_final == 1

            stats3 = await backfill_growth_validation(session, dry_run=True)
            assert stats3.skipped_existing_final == 1

    asyncio.run(_run())
