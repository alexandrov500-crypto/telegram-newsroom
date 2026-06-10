"""Pre-publication growth advisor orchestration."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.growth_layer.editorial.scorecard import evaluate_post_editorial_score
from app.growth_layer.prepublish.context import load_historical_rows, load_segment_discovery
from app.growth_layer.prepublish.draft_analyzer import analyze_draft_growth_potential
from app.growth_layer.prepublish.recommendations import generate_growth_recommendations


def growth_advisor_enabled() -> bool:
    return os.getenv("GROWTH_ADVISOR_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def score_tier(score: int) -> str:
    if score >= 85:
        return "strong"
    if score >= 70:
        return "good"
    if score >= 40:
        return "moderate"
    return "weak"


def evaluate_growth_alignment(
    draft: Any,
    *,
    runtime_dir: str | Path | None = None,
    discovery: dict[str, Any] | None = None,
    historical_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score draft alignment with segment winning patterns (0–100)."""
    analysis = analyze_draft_growth_potential(draft)
    segment = str(analysis.get("content_segment") or "general_news")
    post = analysis.get("post") or {}

    if discovery is None:
        discovery, _, _ = load_segment_discovery(
            segment,
            runtime_dir=runtime_dir,
            historical_rows=historical_rows,
        )

    scorecard = evaluate_post_editorial_score(post, segment_discovery=discovery)
    score = int(scorecard.get("score") or 0)
    return {
        "score": score,
        "headline_alignment": int(scorecard.get("headline_quality") or 0),
        "structure_alignment": int(scorecard.get("structure_quality") or 0),
        "segment_alignment": int(scorecard.get("segment_alignment") or 0),
        "tier": score_tier(score),
        "content_segment": segment,
    }


def evaluate_draft(
    draft: Any,
    *,
    runtime_dir: str | Path | None = None,
    historical_rows: list[dict[str, Any]] | None = None,
    discovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full pre-publication growth advisor payload.
    Analysis-only — does not modify content or block publish.
    """
    analysis = analyze_draft_growth_potential(draft)
    segment = str(analysis.get("content_segment") or "general_news")

    if discovery is None:
        discovery, data_source, sample_size = load_segment_discovery(
            segment,
            runtime_dir=runtime_dir,
            historical_rows=historical_rows,
        )
    else:
        data_source = "provided"
        sample_size = int(discovery.get("sample_size") or 0)

    alignment = evaluate_growth_alignment(
        draft,
        runtime_dir=runtime_dir,
        discovery=discovery,
        historical_rows=historical_rows,
    )
    recs = generate_growth_recommendations(
        analysis,
        discovery=discovery,
        segment=segment,
        runtime_dir=str(runtime_dir) if runtime_dir is not None else None,
    )

    return {
        "alignment": alignment,
        "segment": segment,
        "format_profile": str(analysis.get("format_profile") or "cb_brief"),
        "features": {
            k: analysis.get(k)
            for k in (
                "headline_length",
                "headline_word_count",
                "has_number",
                "has_question",
                "has_quote",
                "paragraph_count",
                "link_count",
                "emoji_count",
            )
        },
        "recommendations": recs.get("recommendations") or [],
        "recommendations_detailed": recs.get("recommendations_detailed") or [],
        "mismatches": recs.get("mismatches") or [],
        "policy_applied": bool(recs.get("policy_applied")),
        "insufficient_data": bool(recs.get("insufficient_data")),
        "sample_size": int(recs.get("sample_size") or sample_size),
        "data_source": data_source,
        "computed_at": datetime.now(UTC).isoformat(),
    }


async def enrich_preview_extras_with_growth_advisor(
    session: Any,
    draft: Any,
    *,
    runtime_dir: str | Path,
) -> dict[str, Any] | None:
    """Compute live growth advisor for preview (does not persist)."""
    if not growth_advisor_enabled():
        return None
    try:
        return await evaluate_draft_with_session(session, draft, runtime_dir=runtime_dir)
    except Exception:
        return None


async def evaluate_draft_with_session(
    session: Any,
    draft: Any,
    *,
    runtime_dir: str | Path,
    historical_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rows = historical_rows if historical_rows is not None else await load_historical_rows(session)
    return evaluate_draft(draft, runtime_dir=runtime_dir, historical_rows=rows)


async def persist_draft_growth_advice(
    session: Any,
    *,
    draft_id: int,
    advice: dict[str, Any],
) -> None:
    from db.growth_advice_repository import upsert_draft_growth_advice

    await upsert_draft_growth_advice(session, draft_id=int(draft_id), advice=advice)


def render_growth_advisor_html(advisor: dict[str, Any]) -> str:
    """Telegram HTML block for draft preview card."""
    from publisher.public_renderer import escape_telegram_html

    if not advisor:
        return ""
    alignment = advisor.get("alignment") if isinstance(advisor.get("alignment"), dict) else {}
    score = alignment.get("score")
    if score is None:
        return ""
    segment = escape_telegram_html(str(advisor.get("segment") or "general").replace("_", " ").title())
    tier = escape_telegram_html(str(alignment.get("tier") or ""))
    lines = [
        "",
        "<b>Growth Alignment Score</b>: "
        f"<code>{int(score)}</code>"
        + (f" ({tier})" if tier else ""),
        f"<b>Segment</b>: {segment}",
    ]
    if advisor.get("insufficient_data"):
        lines.append("<i>Insufficient historical data for segment-specific patterns.</i>")
        return "\n".join(lines)
    recs = advisor.get("recommendations") if isinstance(advisor.get("recommendations"), list) else []
    if recs:
        lines.append("<b>Recommendations</b>:")
        for rec in recs[:5]:
            text = str(rec)
            if " — " in text:
                action, evidence = text.split(" — ", 1)
                lines.append(f"• {escape_telegram_html(action)}")
                lines.append(f"  <i>{escape_telegram_html(evidence[:220])}</i>")
            else:
                lines.append(f"• {escape_telegram_html(text[:260])}")
    else:
        lines.append("<b>Recommendations</b>: aligned with segment winning patterns")
    return "\n".join(lines)
