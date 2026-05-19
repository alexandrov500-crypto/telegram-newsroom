from __future__ import annotations

from bot.editorial.memory.context_snippet import build_context_snippet
from bot.editorial.memory.contradiction import detect_contradictions, detect_tone_direction
from bot.editorial.memory.follow_up import classify_follow_up
from bot.editorial.memory.matching import pick_storyline
from bot.editorial.memory.repository import EditorialMemoryRepository
from bot.editorial.memory.saturation import compute_saturation
from bot.editorial.memory.types import EditorialMemoryReport, FOLLOW_UP_NEW
from bot.editorial.memory.warnings import build_memory_warnings


def _framing_hint(
    *,
    follow_up_kind: str,
    publish_count: int,
    headline: str,
    storyline_title: str | None,
) -> str | None:
    if follow_up_kind in ("duplicate", "minor_variation"):
        return "Consider skipping or merging — low incremental value."
    if follow_up_kind == "follow_up" and publish_count >= 2:
        return (
            f"Frame as an update to {storyline_title or 'ongoing coverage'} "
            f"with what changed since the last post."
        )
    if follow_up_kind == "historical_context":
        return "Note the gap since last coverage; anchor readers briefly."
    if follow_up_kind == FOLLOW_UP_NEW and len(headline) < 40:
        return "Headline may be too vague for a developing storyline — add specificity."
    return None


def analyze_editorial_memory(
    *,
    headline: str,
    summary: str,
    tags: list[str],
    source: str | None,
    repo: EditorialMemoryRepository,
    cluster_id: int | None = None,
) -> EditorialMemoryReport:
    """Synchronous advisory analysis for preview and background record."""
    candidates = repo.active_storylines()
    storyline, match_score, default_id = pick_storyline(
        headline=headline,
        summary=summary,
        tags=tags,
        candidates=candidates,
    )

    is_new_storyline = storyline is None
    storyline_id = default_id if is_new_storyline else storyline.storyline_id
    storyline_title = storyline.title if storyline else None
    publish_count = storyline.publish_count if storyline else 0

    follow_up_kind = classify_follow_up(
        match_score=match_score,
        storyline=storyline,
        headline=headline,
        summary=summary,
    )

    prior_text = None
    prior_tone = None
    if storyline:
        prior_text = f"{storyline.latest_headline or ''} {storyline.latest_summary or ''}"
        prior_tone = storyline.tone_direction

    contradiction_flags = tuple(
        detect_contradictions(
            prior_text=prior_text,
            prior_tone=prior_tone,
            new_text=f"{headline} {summary}",
        ),
    )

    count_72h = repo.publish_count_72h(storyline_id) if not is_new_storyline else 0
    saturation = compute_saturation(
        publish_count_72h=count_72h + (0 if follow_up_kind == "duplicate" else 1),
        publish_count_total=publish_count + 1,
    )

    context_snippet = build_context_snippet(
        storyline=storyline,
        follow_up_kind=follow_up_kind,
        headline=headline,
    )

    report = EditorialMemoryReport(
        storyline_id=storyline_id,
        storyline_title=storyline_title,
        follow_up_kind=follow_up_kind,
        context_snippet=context_snippet,
        saturation_score=saturation,
        contradiction_flags=contradiction_flags,
        publish_count=publish_count,
        match_score=match_score,
        framing_hint=_framing_hint(
            follow_up_kind=follow_up_kind,
            publish_count=publish_count,
            headline=headline,
            storyline_title=storyline_title,
        ),
        metadata={"cluster_id": cluster_id, "is_new_storyline": is_new_storyline},
    )
    warnings = build_memory_warnings(report)
    return EditorialMemoryReport(
        storyline_id=report.storyline_id,
        storyline_title=report.storyline_title,
        follow_up_kind=report.follow_up_kind,
        context_snippet=report.context_snippet,
        warnings=warnings,
        saturation_score=report.saturation_score,
        contradiction_flags=report.contradiction_flags,
        publish_count=report.publish_count,
        match_score=report.match_score,
        framing_hint=report.framing_hint,
        metadata=report.metadata,
    )
