"""Tests for Growth Layer editorial intelligence (Phase 2C)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.growth_layer.editorial.api import get_segment_editorial_recommendations
from app.growth_layer.editorial.editorial_recommendations import (
    generate_editorial_recommendations,
    recommendations_as_bullets,
)
from app.growth_layer.editorial.feature_extraction import (
    draft_to_post_dict,
    extract_editorial_features,
)
from app.growth_layer.editorial.pattern_discovery import (
    discover_all_segment_patterns,
    discover_growth_patterns,
)
from app.growth_layer.editorial.scorecard import evaluate_post_editorial_score
from app.growth_layer.editorial.snapshot import (
    build_editorial_intelligence_snapshot,
    load_editorial_intelligence_snapshot,
    persist_editorial_intelligence_snapshot,
)
from app.growth_layer.validation.weekly_report import build_weekly_growth_report
from db.editorial_features_repository import features_to_row_fields, upsert_post_editorial_features
from db.session import close_db, init_db, session_scope


def _perf_row(
    draft_id: int,
    *,
    segment: str = "technology",
    err: float = 0.5,
    forwards: int = 5,
    engagement: float = 0.4,
    **features: object,
) -> dict:
    base = {
        "draft_id": draft_id,
        "content_segment": segment,
        "validation_status": "FINAL",
        "actual_err": err,
        "actual_forwards": forwards,
        "actual_engagement": engagement,
        "actual_forward_rate": forwards / 100.0,
        "format_profile": "growth_brief",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "headline_length": 40,
        "headline_word_count": 8,
        "has_number": False,
        "has_percent": False,
        "has_currency": False,
        "has_question": False,
        "has_colon": False,
        "has_quote": False,
        "uppercase_ratio": 0.05,
        "body_length": 500,
        "paragraph_count": 4,
        "bullet_count": 0,
        "emoji_count": 0,
        "link_count": 1,
        "source_count": 2,
    }
    base.update(features)
    return base


def _cohort(*, n: int = 25, segment: str = "technology", winners_use_numbers: bool = True) -> list[dict]:
    rows: list[dict] = []
    top_k = max(1, int(round(n * 0.2)))
    for i in range(n):
        is_top = i < top_k
        rows.append(
            _perf_row(
                draft_id=i,
                segment=segment,
                err=0.85 if is_top else 0.12,
                forwards=20 if is_top else 2,
                engagement=0.7 if is_top else 0.2,
                has_number=is_top if winners_use_numbers else not is_top,
                has_question=not is_top if winners_use_numbers else is_top,
                headline_word_count=45 if is_top else 12,
                paragraph_count=5 if is_top else 2,
                link_count=1 if is_top else 4,
            )
        )
    return rows


# --- Feature extraction ---


def test_extract_headline_number_percent_currency() -> None:
    post = draft_to_post_dict(
        draft_id=1,
        content="Title\n\nBody",
        editor_title="Bitcoin +12% hits $50,000",
    )
    feats = extract_editorial_features(post)
    assert feats["has_number"] is True
    assert feats["has_percent"] is True
    assert feats["has_currency"] is True


def test_extract_headline_question_and_quote() -> None:
    post = draft_to_post_dict(draft_id=2, content="", editor_title='«Who wins the race?»')
    feats = extract_editorial_features(post)
    assert feats["has_question"] is True
    assert feats["has_quote"] is True


def test_extract_headline_colon_and_uppercase_ratio() -> None:
    post = draft_to_post_dict(draft_id=3, content="", editor_title="BREAKING: Markets surge")
    feats = extract_editorial_features(post)
    assert feats["has_colon"] is True
    assert feats["uppercase_ratio"] > 0.3


def test_extract_body_paragraphs_and_bullets() -> None:
    body = "Para one.\n\nPara two.\n\n• bullet A\n- bullet B"
    post = draft_to_post_dict(draft_id=4, content=f"Headline\n\n{body}", editor_summary=body)
    feats = extract_editorial_features(post)
    assert feats["paragraph_count"] >= 2
    assert feats["bullet_count"] >= 2


def test_extract_link_and_emoji_counts() -> None:
    body = "Read https://example.com/news and t.me/channel 🔥"
    post = draft_to_post_dict(draft_id=5, content=f"Title\n\n{body}", editor_summary=body)
    feats = extract_editorial_features(post)
    assert feats["link_count"] >= 2
    assert feats["emoji_count"] >= 1


def test_extract_source_count_from_json_list() -> None:
    post = draft_to_post_dict(
        draft_id=6,
        content="Title\n\nBody",
        sources=json.dumps([{"url": "a"}, {"url": "b"}, {"url": "c"}]),
    )
    feats = extract_editorial_features(post)
    assert feats["source_count"] == 3


def test_extract_metadata_from_draft_extras() -> None:
    extras = json.dumps(
        {
            "content_segment": "war",
            "growth": {"format_profile": "growth_brief", "virality_tier": "viral"},
        }
    )
    post = draft_to_post_dict(draft_id=7, content="Head\n\nBody", draft_extras=extras)
    feats = extract_editorial_features(post)
    assert feats["content_segment"] == "war"
    assert feats["format_profile"] == "growth_brief"
    assert feats["virality_tier"] == "viral"


def test_extract_splits_content_when_no_editor_fields() -> None:
    post = draft_to_post_dict(draft_id=8, content="Short headline\n\nFirst paragraph.\n\nSecond paragraph.")
    feats = extract_editorial_features(post)
    assert feats["headline_word_count"] == 2
    assert feats["paragraph_count"] >= 2


def test_extract_empty_post_defaults() -> None:
    feats = extract_editorial_features({})
    assert feats["headline_length"] == 0
    assert feats["body_length"] == 0
    assert feats["content_segment"] == "general_news"


def test_features_to_row_fields_roundtrip() -> None:
    feats = extract_editorial_features(
        draft_to_post_dict(draft_id=9, content="5 facts\n\nBody", editor_title="5 facts")
    )
    row = features_to_row_fields(feats)
    assert row["has_number"] == 1
    assert row["content_segment"] == "general_news"
    assert json.loads(row["features_json"])["has_number"] is True


# --- Pattern discovery ---


def test_discover_patterns_top_vs_bottom_by_err() -> None:
    rows = _cohort(n=25)
    result = discover_growth_patterns(rows, metric="err")
    assert result["sample_size"] == 25
    assert result["top_count"] == 5
    assert result["bottom_count"] == 5
    numbers = result["patterns"]["has_number"]
    assert numbers["top"] > numbers["bottom"]
    assert numbers["lift"] is not None and numbers["lift"] > 0


def test_discover_patterns_respects_segment_filter() -> None:
    rows = _cohort(n=20, segment="technology")
    rows.extend(_cohort(n=20, segment="war", winners_use_numbers=False))
    tech = discover_growth_patterns(rows, segment="technology")
    war = discover_growth_patterns(rows, segment="war")
    assert tech["sample_size"] == 20
    assert war["sample_size"] == 20


def test_discover_patterns_forwards_metric() -> None:
    rows = _cohort(n=15)
    result = discover_growth_patterns(rows, metric="forwards")
    assert result["metric"] == "forwards"
    assert result["patterns"]["has_number"]["top"] >= result["patterns"]["has_number"]["bottom"]


def test_discover_patterns_insufficient_sample() -> None:
    result = discover_growth_patterns([_perf_row(1, err=0.5)], metric="err")
    assert result["patterns"] == {}
    assert result["top_count"] == 0


def test_discover_all_segment_patterns_includes_all_and_segments() -> None:
    rows = _cohort(n=20, segment="technology")
    rows.extend(_cohort(n=20, segment="markets"))
    out = discover_all_segment_patterns(rows)
    assert "all" in out
    assert "technology" in out
    assert "markets" in out


def test_discover_numeric_patterns_include_top_range() -> None:
    rows = _cohort(n=25)
    result = discover_growth_patterns(rows)
    wc = result["numeric_patterns"]["headline_word_count"]
    assert wc["top_mean"] > wc["bottom_mean"]
    assert wc["top_range"]["low"] is not None


def test_discover_acquisition_score_metric_fallback() -> None:
    row = _perf_row(1, err=0.9, forwards=50)
    row.pop("acquisition_proxy_score", None)
    rows = [row] * 10
    for i, r in enumerate(rows):
        r["draft_id"] = i
        r["actual_err"] = 0.9 - i * 0.08
    result = discover_growth_patterns(rows, metric="acquisition_score")
    assert result["sample_size"] == 10


# --- Recommendations ---


def test_generate_editorial_recommendations_winning_patterns() -> None:
    rows = _cohort(n=30, segment="technology")
    recs = generate_editorial_recommendations(rows)
    tech = recs["technology"]
    assert tech["winning_patterns"]
    assert any("numeric" in w.lower() or "number" in w.lower() for w in tech["winning_patterns"])


def test_generate_editorial_recommendations_anti_patterns() -> None:
    rows = _cohort(n=30, segment="technology")
    recs = generate_editorial_recommendations(rows)
    tech = recs["technology"]
    assert tech["anti_patterns"]
    assert any("question" in a.lower() for a in tech["anti_patterns"])


def test_segment_specific_war_patterns() -> None:
    rows = _cohort(n=25, segment="war", winners_use_numbers=False)
    for i, r in enumerate(rows):
        is_top = i < 5
        r["headline_word_count"] = 60 if is_top else 8
        r["headline_length"] = 60 if is_top else 8
    recs = generate_editorial_recommendations(rows)
    war = recs.get("war") or {}
    assert "discovery" in war


def test_recommendations_as_bullets_helper() -> None:
    data = {"winning_patterns": ["A"], "anti_patterns": ["B"]}
    winning, anti = recommendations_as_bullets(data)
    assert winning == ["A"]
    assert anti == ["B"]


def test_get_segment_editorial_recommendations_from_rows() -> None:
    rows = _cohort(n=30, segment="technology")
    recs = get_segment_editorial_recommendations("technology", rows=rows)
    assert isinstance(recs, list)
    assert len(recs) >= 1


# --- Scorecard ---


def test_evaluate_post_editorial_score_structure() -> None:
    rows = _cohort(n=25, segment="technology")
    discovery = discover_growth_patterns(rows, segment="technology")
    post = draft_to_post_dict(
        draft_id=99,
        content="",
        editor_title="10 AI tools reshape 2026",
        editor_summary="Para one.\n\nPara two.\n\nPara three.\n\nPara four.",
        content_segment="technology",
    )
    result = evaluate_post_editorial_score(post, segment_discovery=discovery)
    assert 0 <= result["score"] <= 100
    assert 0 <= result["headline_quality"] <= 100
    assert 0 <= result["structure_quality"] <= 100
    assert 0 <= result["segment_alignment"] <= 100
    assert result["content_segment"] == "technology"
    assert result["features"]["has_number"] is True


def test_scorecard_higher_for_aligned_post() -> None:
    rows = _cohort(n=25, segment="technology")
    discovery = discover_growth_patterns(rows, segment="technology")
    aligned = draft_to_post_dict(
        draft_id=100,
        content="",
        editor_title="42 startups raised funding in Q1",
        editor_summary="\n\n".join(["Paragraph"] * 5),
        content_segment="technology",
    )
    misaligned = draft_to_post_dict(
        draft_id=101,
        content="",
        editor_title="Why?",
        editor_summary="Short.",
        content_segment="technology",
    )
    aligned_score = evaluate_post_editorial_score(aligned, segment_discovery=discovery)["score"]
    misaligned_score = evaluate_post_editorial_score(misaligned, segment_discovery=discovery)["score"]
    assert aligned_score >= misaligned_score


def test_scorecard_default_discovery_single_post() -> None:
    post = draft_to_post_dict(draft_id=102, content="Headline\n\nBody text.", content_segment="markets")
    result = evaluate_post_editorial_score(post)
    assert "score" in result


# --- Snapshot & API ---


def test_build_editorial_intelligence_snapshot_shape() -> None:
    rows = _cohort(n=25, segment="technology")
    snapshot = build_editorial_intelligence_snapshot(rows)
    assert snapshot["generated_from_posts"] == 25
    assert "technology" in snapshot["segments"]
    assert "winning_patterns" in snapshot["segments"]["technology"]
    assert "global" in snapshot


def test_persist_and_load_editorial_snapshot(tmp_path: Path) -> None:
    rows = _cohort(n=20, segment="science")
    persist_editorial_intelligence_snapshot(tmp_path, rows)
    loaded = load_editorial_intelligence_snapshot(tmp_path)
    assert loaded["generated_from_posts"] == 20
    assert "science" in loaded["segments"]


def test_get_segment_editorial_recommendations_from_snapshot(tmp_path: Path) -> None:
    rows = _cohort(n=25, segment="politics")
    persist_editorial_intelligence_snapshot(tmp_path, rows)
    recs = get_segment_editorial_recommendations("politics", runtime_dir=tmp_path)
    assert isinstance(recs, list)


def test_get_segment_editorial_recommendations_fallback_global(tmp_path: Path) -> None:
    snapshot = {
        "segments": {},
        "global": {"winning_patterns": ["Prefer concise headlines"], "anti_patterns": []},
    }
    path = tmp_path / "editorial_intelligence.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    recs = get_segment_editorial_recommendations("unknown_segment", runtime_dir=tmp_path)
    assert recs == ["Prefer concise headlines"]


# --- Weekly report integration ---


def test_weekly_report_includes_editorial_intelligence_section() -> None:
    rows = _cohort(n=30, segment="technology")
    html = build_weekly_growth_report(week_rows=rows, all_rows=rows, editorial_rows=rows)
    assert "EDITORIAL INTELLIGENCE" in html
    assert "Technology" in html
    assert "Winning patterns" in html


def test_weekly_report_editorial_empty_when_no_rows() -> None:
    html = build_weekly_growth_report(week_rows=[], all_rows=[], editorial_rows=[])
    assert "EDITORIAL INTELLIGENCE" in html
    assert "Недостаточно данных" in html


# --- DB backfill / repository ---


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'editorial_intel.db'}"


def test_upsert_post_editorial_features(sqlite_url: str) -> None:
    async def _run() -> None:
        await init_db(sqlite_url)
        async with session_scope() as session:
            from db.models import Draft
            from db.repository import utcnow

            draft = Draft(
                content="5 trends\n\nBody paragraph.",
                content_hash="edhash",
                sources="[]",
                created_at=utcnow(),
            )
            session.add(draft)
            await session.flush()
            feats = extract_editorial_features(
                draft_to_post_dict(draft_id=int(draft.id), content=draft.content or "")
            )
            row = await upsert_post_editorial_features(session, draft_id=int(draft.id), features=feats)
            assert row.draft_id == draft.id
            assert row.has_number == 1
        await close_db()

    asyncio.run(_run())
