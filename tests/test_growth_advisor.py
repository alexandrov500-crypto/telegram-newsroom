"""Tests for Phase 3A Pre-Publication Growth Advisor."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.growth_layer.prepublish.context import discovery_from_snapshot, load_segment_discovery
from app.growth_layer.prepublish.draft_analyzer import analyze_draft_growth_potential
from app.growth_layer.prepublish.growth_advisor import (
    evaluate_draft,
    evaluate_growth_alignment,
    growth_advisor_enabled,
    render_growth_advisor_html,
    score_tier,
)
from app.growth_layer.prepublish.insights import build_prepublication_insights
from app.growth_layer.prepublish.recommendations import generate_growth_recommendations
from app.growth_layer.validation.weekly_report import build_weekly_growth_report
from db.growth_advice_repository import get_draft_growth_advice, upsert_draft_growth_advice
from db.session import close_db, init_db, session_scope


def _cohort(*, n: int = 25, segment: str = "technology", winners_use_numbers: bool = True) -> list[dict]:
    rows: list[dict] = []
    top_k = max(1, int(round(n * 0.2)))
    for i in range(n):
        is_top = i < top_k
        rows.append(
            {
                "draft_id": i,
                "content_segment": segment,
                "validation_status": "FINAL",
                "actual_err": 0.85 if is_top else 0.12,
                "actual_forwards": 20 if is_top else 2,
                "actual_engagement": 0.7 if is_top else 0.2,
                "has_number": is_top if winners_use_numbers else not is_top,
                "has_question": not is_top if winners_use_numbers else is_top,
                "headline_word_count": 45 if is_top else 12,
                "paragraph_count": 5 if is_top else 2,
                "link_count": 1 if is_top else 4,
                "headline_length": 50 if is_top else 15,
                "body_length": 800 if is_top else 200,
                "emoji_count": 0,
                "format_profile": "growth_brief",
            }
        )
    return rows


def _draft(
    *,
    draft_id: int = 1,
    title: str = "Plain headline without numbers",
    body: str = "Para one.\n\nPara two.\n\nPara three.\n\nPara four.\n\nPara five.\n\nPara six.\n\nPara seven.\n\nPara eight.",
    segment: str = "technology",
    links: str = "",
) -> dict:
    if links:
        body = f"{body}\n\n{links}"
    extras = json.dumps({"growth": {"format_profile": "growth_brief"}, "category": segment})
    return {
        "draft_id": draft_id,
        "content": f"{title}\n\n{body}",
        "sources": "[]",
        "draft_extras": extras,
        "editor_title": title,
        "editor_summary": body,
        "content_segment": segment,
    }


def _discovery_from_rows(rows: list[dict], segment: str = "technology") -> dict:
    from app.growth_layer.editorial.pattern_discovery import discover_growth_patterns

    return discover_growth_patterns(rows, segment=segment)


# --- Draft analyzer ---


def test_analyze_draft_extracts_features() -> None:
    analysis = analyze_draft_growth_potential(_draft(title="10 AI tools reshape markets"))
    assert analysis["has_number"] is True
    assert analysis["content_segment"] == "technology"
    assert analysis["paragraph_count"] >= 1


def test_analyze_draft_detects_links() -> None:
    analysis = analyze_draft_growth_potential(
        _draft(links="See https://a.com and https://b.com and https://c.com and https://d.com")
    )
    assert analysis["link_count"] >= 4


def test_analyze_draft_detects_question_headline() -> None:
    analysis = analyze_draft_growth_potential(_draft(title="Who wins the AI race?"))
    assert analysis["has_question"] is True


def test_analyze_draft_format_profile_from_extras() -> None:
    analysis = analyze_draft_growth_potential(_draft())
    assert analysis["format_profile"] == "growth_brief"


def test_analyze_draft_accepts_orm_like_object() -> None:
    class _Draft:
        id = 7
        content = "5 facts\n\nBody"
        sources = "[]"
        draft_extras = "{}"
        editor_title = "5 facts"
        editor_summary = "Body"

    analysis = analyze_draft_growth_potential(_Draft())
    assert analysis["draft_id"] == 7
    assert analysis["has_number"] is True


# --- Context loading ---


def test_discovery_from_snapshot_reads_recommendations() -> None:
    snapshot = {
        "recommendations": {
            "technology": {
                "discovery": {"patterns": {"has_number": {"top": 0.8, "bottom": 0.2, "lift": 100}}, "sample_size": 50}
            }
        }
    }
    disc = discovery_from_snapshot(snapshot, "technology")
    assert disc is not None
    assert disc["patterns"]["has_number"]["lift"] == 100


def test_load_segment_discovery_from_historical_rows() -> None:
    rows = _cohort(n=25)
    disc, source, sample = load_segment_discovery("technology", historical_rows=rows)
    assert source == "live_discovery"
    assert sample == 25
    assert disc["patterns"]["has_number"]["top"] > disc["patterns"]["has_number"]["bottom"]


def test_load_segment_discovery_insufficient_data() -> None:
    disc, source, sample = load_segment_discovery("technology", historical_rows=[])
    assert source == "insufficient_data"
    assert sample == 0


# --- Alignment scoring ---


def test_score_tier_bands() -> None:
    assert score_tier(90) == "strong"
    assert score_tier(75) == "good"
    assert score_tier(55) == "moderate"
    assert score_tier(30) == "weak"


def test_evaluate_growth_alignment_returns_fields() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    aligned = _draft(title="42 startups raised funding in Q1", body="\n\n".join(["Paragraph"] * 5))
    result = evaluate_growth_alignment(aligned, discovery=discovery)
    assert 0 <= result["score"] <= 100
    assert 0 <= result["headline_alignment"] <= 100
    assert 0 <= result["structure_alignment"] <= 100
    assert 0 <= result["segment_alignment"] <= 100
    assert result["tier"] in ("weak", "moderate", "good", "strong")


def test_aligned_draft_scores_higher_than_misaligned() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    aligned = evaluate_growth_alignment(
        _draft(title="42 AI tools hit market", body="\n\n".join(["P"] * 5), links=""),
        discovery=discovery,
    )
    misaligned = evaluate_growth_alignment(
        _draft(title="Why?", body="Short.", links="https://a.com https://b.com https://c.com https://d.com"),
        discovery=discovery,
    )
    assert aligned["score"] >= misaligned["score"]


# --- Recommendations ---


def test_generate_recommendations_missing_number() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    analysis = analyze_draft_growth_potential(_draft(title="Markets surge without figures"))
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    assert recs["recommendations"]
    assert any("numeric" in r.lower() or "number" in r.lower() for r in recs["recommendations"])


def test_generate_recommendations_excess_links() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    analysis = analyze_draft_growth_potential(
        _draft(links="https://a.com https://b.com https://c.com https://d.com")
    )
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    assert any("link" in r.lower() for r in recs["recommendations"])


def test_generate_recommendations_include_evidence() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    analysis = analyze_draft_growth_potential(_draft(title="No numbers here"))
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    for item in recs["recommendations_detailed"]:
        assert item.get("evidence")
        assert "historically" in item["evidence"].lower() or "lift" in item["evidence"].lower()


def test_generate_recommendations_insufficient_sample() -> None:
    analysis = analyze_draft_growth_potential(_draft())
    recs = generate_growth_recommendations(
        analysis,
        discovery={"patterns": {}, "numeric_patterns": {}, "sample_size": 2},
    )
    assert recs["insufficient_data"] is True
    assert recs["recommendations"] == []


def test_generate_recommendations_no_evidence_without_lift() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    for key in list((discovery.get("patterns") or {}).keys()):
        discovery["patterns"][key]["lift"] = 5
    for key in list((discovery.get("numeric_patterns") or {}).keys()):
        discovery["numeric_patterns"][key]["lift"] = 5
    analysis = analyze_draft_growth_potential(_draft(title="No numbers"))
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    assert recs["recommendations"] == []


def test_generate_recommendations_paragraph_mismatch() -> None:
    rows = _cohort(n=25)
    discovery = _discovery_from_rows(rows)
    long_body = "\n\n".join([f"Paragraph {i}" for i in range(10)])
    analysis = analyze_draft_growth_potential(_draft(body=long_body))
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    assert any("paragraph" in r.lower() for r in recs["recommendations"])


# --- Full evaluate_draft ---


def test_evaluate_draft_full_payload() -> None:
    rows = _cohort(n=25)
    advice = evaluate_draft(_draft(), historical_rows=rows)
    assert "alignment" in advice
    assert "recommendations" in advice
    assert advice["segment"] == "technology"
    assert advice["computed_at"]
    assert advice["data_source"] in ("live_discovery", "live_discovery_global", "insufficient_data")


def test_evaluate_draft_includes_mismatches() -> None:
    rows = _cohort(n=25)
    advice = evaluate_draft(_draft(title="No numbers", links="https://x.com https://y.com https://z.com https://w.com"), historical_rows=rows)
    assert isinstance(advice["mismatches"], list)


# --- Preview HTML ---


def test_render_growth_advisor_html_shows_score() -> None:
    advice = {
        "segment": "technology",
        "alignment": {"score": 74, "tier": "good"},
        "recommendations": ["Add numbers — Technology posts with numbers showed +22% ERR historically."],
    }
    html = render_growth_advisor_html(advice)
    assert "Growth Alignment Score" in html
    assert "74" in html
    assert "Technology" in html
    assert "Recommendations" in html


def test_render_growth_advisor_html_insufficient_data() -> None:
    html = render_growth_advisor_html(
        {"segment": "war", "alignment": {"score": 50, "tier": "moderate"}, "insufficient_data": True}
    )
    assert "Insufficient historical data" in html


def test_render_growth_advisor_html_empty_when_no_score() -> None:
    assert render_growth_advisor_html({}) == ""


# --- Weekly report ---


def test_weekly_report_prepublication_insights_section() -> None:
    rows = _cohort(n=20)
    advice_rows = [
        {"draft_id": i, "alignment_score": 90 if i < 5 else 45, "predicted_segment": "technology"}
        for i in range(20)
    ]
    html = build_weekly_growth_report(
        week_rows=rows,
        all_rows=rows,
        editorial_rows=rows,
        advice_rows=advice_rows,
    )
    assert "PRE-PUBLICATION INSIGHTS" in html
    assert "Average Alignment Score" in html


def test_prepublication_insights_aggregation() -> None:
    advice = [{"draft_id": i, "alignment_score": 90 if i < 3 else 40, "predicted_segment": "technology"} for i in range(10)]
    validation = [
        {"draft_id": i, "actual_err": 0.8 if i < 3 else 0.3, "validation_status": "FINAL", "content_segment": "technology"}
        for i in range(10)
    ]
    stats = build_prepublication_insights(advice, validation)
    assert stats["sample_size"] == 10
    assert stats["average_alignment_score"] is not None
    assert stats["strong_lift_pct"] is not None
    assert stats["weak_lift_pct"] is not None


def test_prepublication_insights_empty_without_join() -> None:
    stats = build_prepublication_insights([{"draft_id": 1, "alignment_score": 80}], [])
    assert stats["sample_size"] == 0


# --- Feature flag ---


def test_growth_advisor_enabled_default() -> None:
    import os

    os.environ.pop("GROWTH_ADVISOR_ENABLED", None)
    assert growth_advisor_enabled() is True


def test_growth_advisor_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROWTH_ADVISOR_ENABLED", "false")
    assert growth_advisor_enabled() is False


# --- Rich preview integration ---


def test_rich_preview_shows_growth_advisor(tmp_path: Path) -> None:
    from publisher.formatting import render_rich_draft_preview_html

    extras = {
        "growth_advisor": {
            "segment": "technology",
            "alignment": {"score": 74, "tier": "good"},
            "recommendations": ["Add numbers — evidence here."],
        }
    }
    html = render_rich_draft_preview_html(
        1,
        "Title\n\nBody",
        "[]",
        draft_extras_json=json.dumps(extras),
    )
    assert "Growth Alignment Score" in html


# --- Persistence ---


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'growth_advisor.db'}"


def test_upsert_draft_growth_advice(sqlite_url: str) -> None:
    async def _run() -> None:
        await init_db(sqlite_url)
        async with session_scope() as session:
            from db.models import Draft
            from db.repository import utcnow

            draft = Draft(content="test", content_hash="ga1", sources="[]", created_at=utcnow())
            session.add(draft)
            await session.flush()
            rows = _cohort(n=25)
            advice = evaluate_draft(
                {
                    "draft_id": int(draft.id),
                    "content": draft.content,
                    "sources": draft.sources,
                    "draft_extras": json.dumps({"category": "technology", "growth": {"format_profile": "growth_brief"}}),
                    "editor_title": "10 facts",
                    "editor_summary": "Body",
                },
                historical_rows=rows,
            )
            await upsert_draft_growth_advice(session, draft_id=int(draft.id), advice=advice)
            stored = await get_draft_growth_advice(session, int(draft.id))
            assert stored is not None
            assert stored["alignment_score"] == advice["alignment"]["score"]
            assert stored["predicted_segment"] == "technology"
            assert isinstance(stored["recommendations"], list)
        await close_db()

    asyncio.run(_run())


def test_advice_repository_roundtrip_fields(sqlite_url: str) -> None:
    async def _run() -> None:
        await init_db(sqlite_url)
        async with session_scope() as session:
            from db.models import Draft
            from db.repository import utcnow

            draft = Draft(content="x", content_hash="ga2", sources="[]", created_at=utcnow())
            session.add(draft)
            await session.flush()
            advice = {
                "segment": "war",
                "alignment": {
                    "score": 68,
                    "headline_alignment": 70,
                    "structure_alignment": 65,
                    "segment_alignment": 69,
                    "tier": "moderate",
                },
                "recommendations": ["Keep headline longer"],
                "recommendations_detailed": [{"text": "Keep headline longer", "evidence": "War posts...", "feature": "headline_length"}],
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "data_source": "test",
                "sample_size": 30,
            }
            row = await upsert_draft_growth_advice(session, draft_id=int(draft.id), advice=advice)
            assert row.headline_alignment == 70
            assert row.structure_alignment == 65
        await close_db()

    asyncio.run(_run())


# --- Segment-specific ---


def test_war_segment_advice() -> None:
    rows = _cohort(n=25, segment="war", winners_use_numbers=False)
    for i, r in enumerate(rows):
        is_top = i < 5
        r["headline_word_count"] = 60 if is_top else 8
        r["headline_length"] = 60 if is_top else 8
    advice = evaluate_draft(_draft(segment="war", title="Short"), historical_rows=rows)
    assert advice["segment"] == "war"


def test_explainability_requires_statistical_basis() -> None:
    rows = _cohort(n=30, segment="technology")
    discovery = _discovery_from_rows(rows)
    analysis = analyze_draft_growth_potential(_draft(title="No numbers"))
    recs = generate_growth_recommendations(analysis, discovery=discovery)
    for text in recs["recommendations"]:
        assert "—" in text
        assert any(word in text.lower() for word in ("historically", "lift", "top", "winning", "showed"))
