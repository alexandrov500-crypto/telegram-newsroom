from __future__ import annotations

import json
import random
from datetime import datetime, timezone

import pytest

from app.growth_layer.segments.content_segments import (
    ALL_SEGMENTS,
    ContentSegment,
    classify_content_segment,
    classify_from_draft_extras,
)
from app.growth_layer.segments.routing import (
    get_recommended_mode_for_segment,
    persist_segment_decisions_snapshot,
)
from app.growth_layer.segments.segment_decision import (
    build_segment_decision_map,
    build_segment_stability,
    evaluate_segment_strategy,
    routing_readiness_score,
)
from app.growth_layer.segments.segment_statistics import build_segment_performance
from app.growth_layer.validation.acquisition_proxy import compute_acquisition_components
from app.growth_layer.validation.weekly_report import build_weekly_growth_report


def _row(
    *,
    draft_id: int,
    fmt: str,
    segment: str,
    err: float,
    forward_rate: float,
    forwards: int = 5,
    engagement: float = 0.4,
) -> dict:
    components = compute_acquisition_components(forwards=float(forwards), err=err, engagement=engagement)
    return {
        "draft_id": draft_id,
        "format_profile": fmt,
        "content_segment": segment,
        "validation_status": "FINAL",
        "snapshot_label": "t24h",
        "actual_engagement": engagement,
        "actual_forwards": forwards,
        "actual_views": max(forwards * 50, 100),
        "actual_err": err,
        "actual_forward_rate": forward_rate,
        **components,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def _tech_cohort(*, n_cb: int = 25, n_growth: int = 25, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n_cb):
        rows.append(
            _row(
                draft_id=i,
                fmt="cb_brief",
                segment="technology",
                err=0.50 + rng.uniform(-0.02, 0.02),
                forward_rate=0.020 + rng.uniform(-0.002, 0.002),
                forwards=3,
            )
        )
    for i in range(n_growth):
        rows.append(
            _row(
                draft_id=100 + i,
                fmt="growth_brief",
                segment="technology",
                err=0.71 + rng.uniform(-0.02, 0.02),
                forward_rate=0.028 + rng.uniform(-0.002, 0.002),
                forwards=10,
                engagement=0.55,
            )
        )
    return rows


def test_classify_technology_from_topic() -> None:
    assert classify_content_segment({"topic": "technology"}) == ContentSegment.TECHNOLOGY.value


def test_classify_markets_from_category() -> None:
    assert classify_content_segment({"category": "markets"}) == ContentSegment.MARKETS.value


def test_classify_war_from_cluster_category() -> None:
    assert classify_content_segment({"cluster": {"category": "war updates"}}) == ContentSegment.WAR.value


def test_classify_from_draft_extras_topic() -> None:
    extras = json.dumps({"topic": "crypto markets"})
    assert classify_from_draft_extras(extras) == ContentSegment.CRYPTO.value


def test_classify_macro_maps_to_economy() -> None:
    assert classify_content_segment({"topic_bucket": "macro"}) == ContentSegment.ECONOMY.value


def test_classify_fallback_general_news() -> None:
    assert classify_content_segment({}) == ContentSegment.GENERAL_NEWS.value


def test_all_segments_enum_values() -> None:
    assert "technology" in ALL_SEGMENTS
    assert "general_news" in ALL_SEGMENTS
    assert len(ALL_SEGMENTS) == 10


def test_build_segment_performance_groups_by_segment() -> None:
    rows = _tech_cohort(n_cb=10, n_growth=10)
    rows.append(_row(draft_id=999, fmt="cb_brief", segment="war", err=0.4, forward_rate=0.02))
    perf = build_segment_performance(rows)
    segments = {p["segment"] for p in perf}
    assert "technology" in segments
    assert "war" in segments
    tech = next(p for p in perf if p["segment"] == "technology")
    assert tech["growth_posts"] == 10
    assert tech["cb_posts"] == 10


def test_build_segment_performance_final_only() -> None:
    rows = _tech_cohort(n_cb=5, n_growth=5)
    rows[0]["validation_status"] = "PENDING"
    perf = build_segment_performance(rows)
    tech = next(p for p in perf if p["segment"] == "technology")
    assert tech["growth_posts"] + tech["cb_posts"] == 9


@pytest.fixture
def segment_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_SEGMENT_MIN_SAMPLE", "10")
    monkeypatch.setenv("GROWTH_SEGMENT_MIN_COHORT", "5")


def test_evaluate_segment_strategy_recommends_growth_brief(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=25, n_growth=25)
    verdict = evaluate_segment_strategy("technology", rows)
    assert verdict["segment"] == "technology"
    assert verdict["recommended_mode"] == "growth_brief"
    assert verdict["statistically_significant"] is True


def test_evaluate_segment_strategy_insufficient_sample(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=3, n_growth=3)
    verdict = evaluate_segment_strategy("technology", rows)
    assert verdict["recommended_mode"] == "hybrid"
    assert verdict["reason"] == "insufficient_segment_sample"


def test_evaluate_segment_strategy_cb_wins_for_war(segment_thresholds: None) -> None:
    rng = random.Random(1)
    rows: list[dict] = []
    for i in range(25):
        rows.append(
            _row(
                draft_id=i,
                fmt="cb_brief",
                segment="war",
                err=0.70 + rng.uniform(-0.02, 0.02),
                forward_rate=0.030 + rng.uniform(-0.002, 0.002),
                forwards=12,
            )
        )
    for i in range(25):
        rows.append(
            _row(
                draft_id=100 + i,
                fmt="growth_brief",
                segment="war",
                err=0.50 + rng.uniform(-0.02, 0.02),
                forward_rate=0.020 + rng.uniform(-0.002, 0.002),
                forwards=3,
            )
        )
    verdict = evaluate_segment_strategy("war", rows)
    assert verdict["recommended_mode"] == "cb_brief"
    assert verdict["statistically_significant"] is True


def test_build_segment_stability_windows(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=40, n_growth=40)
    stability = build_segment_stability(rows, "technology")
    assert "last_30" in stability["windows"]
    assert "all_time" in stability["windows"]


def test_strategy_consistency_lowers_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_SEGMENT_MIN_SAMPLE", "5")
    monkeypatch.setenv("GROWTH_SEGMENT_MIN_COHORT", "3")
    recent = _tech_cohort(n_cb=8, n_growth=8, seed=1)
    old: list[dict] = []
    rng = random.Random(9)
    for i in range(8):
        old.append(
            _row(
                draft_id=500 + i,
                fmt="cb_brief",
                segment="technology",
                err=0.70 + rng.uniform(-0.01, 0.01),
                forward_rate=0.030,
                forwards=10,
            )
        )
    for i in range(8):
        old.append(
            _row(
                draft_id=600 + i,
                fmt="growth_brief",
                segment="technology",
                err=0.50 + rng.uniform(-0.01, 0.01),
                forward_rate=0.020,
                forwards=3,
            )
        )
    verdict = evaluate_segment_strategy("technology", recent + old)
    if not verdict["strategy_consistency"]:
        assert verdict["confidence"] == "LOW"


def test_routing_readiness_score_range() -> None:
    score = routing_readiness_score(
        sample_size=120,
        growth_sample=60,
        cb_sample=60,
        effect_size="medium",
        strategy_consistent=True,
        confidence="HIGH",
        statistically_significant=True,
    )
    assert 0 <= score <= 100
    assert score >= 60


def test_routing_readiness_penalizes_insignificance() -> None:
    sig = routing_readiness_score(
        sample_size=120,
        growth_sample=60,
        cb_sample=60,
        effect_size="medium",
        strategy_consistent=True,
        confidence="HIGH",
        statistically_significant=True,
    )
    insig = routing_readiness_score(
        sample_size=120,
        growth_sample=60,
        cb_sample=60,
        effect_size="medium",
        strategy_consistent=True,
        confidence="HIGH",
        statistically_significant=False,
    )
    assert insig < sig


def test_get_recommended_mode_from_live_rows(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=25, n_growth=25)
    rec = get_recommended_mode_for_segment("technology", rows=rows)
    assert rec["source"] == "live_rows"
    assert rec["recommended_mode"] == "growth_brief"


def test_get_recommended_mode_from_snapshot(tmp_path) -> None:
    snapshot = {
        "segments": {
            "technology": {
                "recommended_mode": "growth_brief",
                "confidence": "HIGH",
                "statistically_significant": True,
                "routing_readiness_score": 91,
            }
        }
    }
    rec = get_recommended_mode_for_segment("technology", runtime_dir=tmp_path, snapshot=snapshot)
    assert rec["recommended_mode"] == "growth_brief"
    assert rec["routing_readiness_score"] == 91


def test_get_recommended_mode_default_unknown_segment() -> None:
    rec = get_recommended_mode_for_segment("unknown_segment_xyz")
    assert rec["recommended_mode"] == "hybrid"
    assert rec["source"] == "default"


def test_persist_segment_decisions_snapshot(tmp_path, segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=25, n_growth=25)
    snapshot = persist_segment_decisions_snapshot(tmp_path, rows)
    assert "technology" in snapshot["segments"]
    assert (tmp_path / "growth_segment_decisions.json").is_file()


def test_build_segment_decision_map_structure(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=15, n_growth=15)
    snap = build_segment_decision_map(rows)
    assert "technology" in snap["segments"]
    assert "recommended_mode" in snap["segments"]["technology"]


def test_segment_backfill_from_draft() -> None:
    import asyncio

    async def _run() -> None:
        from sqlalchemy import select

        from app.growth_layer.segments.backfill import backfill_content_segments
        from db.models import Draft, DraftStatus, PostGrowthValidation
        from db.repository import utcnow
        from db.session import init_db, session_scope

        await init_db("sqlite+aiosqlite:///:memory:")
        now = utcnow()
        async with session_scope() as session:
            draft = Draft(
                content="tech story",
                content_hash="seg1",
                sources="[]",
                draft_extras=json.dumps({"topic": "technology", "category": "tech"}),
                status=DraftStatus.PUBLISHED.value,
                created_at=now,
            )
            session.add(draft)
            await session.flush()
            session.add(
                PostGrowthValidation(
                    draft_id=int(draft.id),
                    telegram_post_id=1,
                    channel_id=1,
                    published_at=now,
                    format_profile="cb_brief",
                    predicted_virality=50,
                    virality_tier="enhanced",
                    topic_bucket="tech",
                    primary_source="@test",
                    content_segment="general_news",
                    created_at=now,
                )
            )
            await session.flush()
            stats = await backfill_content_segments(session, dry_run=False)
            assert stats.updated == 1
            row = (
                await session.execute(
                    select(PostGrowthValidation).where(PostGrowthValidation.draft_id == int(draft.id))
                )
            ).scalar_one()
            assert row.content_segment == ContentSegment.TECHNOLOGY.value

    asyncio.run(_run())


def test_weekly_report_includes_segment_section(segment_thresholds: None) -> None:
    rows = _tech_cohort(n_cb=25, n_growth=25)
    html = build_weekly_growth_report(week_rows=rows, all_rows=rows)
    assert "SEGMENT PERFORMANCE" in html
    assert "Technology" in html
