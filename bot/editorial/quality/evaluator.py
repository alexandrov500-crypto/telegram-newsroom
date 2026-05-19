from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bot.editorial.presentation import build_publish_presentation
from bot.editorial.quality.drift import compute_drift_signals
from bot.editorial.quality.fatigue import compute_fatigue_metrics
from bot.editorial.quality.repository import EditorialQualityRepository
from bot.editorial.quality.scoring import EditorialQualityResult, evaluate_editorial_quality
from bot.editorial.quality.warnings import build_quality_warnings


@dataclass(frozen=True, slots=True)
class EditorialQualityReport:
    editorial_quality_score: float
    dimensions: dict[str, float]
    warnings: tuple[str, ...]
    fatigue: dict[str, float]
    drift: dict[str, float]
    weak_phrases: tuple[str, ...] = ()
    template_key: str = "economy"
    metadata: dict[str, Any] = field(default_factory=dict)


def evaluate_post(
    *,
    headline: str,
    summary: str,
    link: str,
    tags: list[str],
    source: str | None,
    hook_line: str | None = None,
    template_key: str | None = None,
    recent: list[dict] | None = None,
    prior_daily: list[dict] | None = None,
) -> EditorialQualityReport:
    pres = build_publish_presentation(
        title=headline,
        summary=summary or "",
        link=link,
        tags=tags,
        source=source,
        hook_line=hook_line,
        template_key=template_key,
    )
    tpl = pres.template.key
    scored: EditorialQualityResult = evaluate_editorial_quality(
        headline=headline,
        summary=summary or "",
        link=link,
        tags=tags,
        source=source,
        template_key=tpl,
        hook_line=hook_line,
    )
    recent_rows = recent or []
    fatigue = compute_fatigue_metrics(
        source=source,
        template_key=tpl,
        tags=tags,
        tone_marker=hook_line,
        recent=recent_rows,
    )
    drift = compute_drift_signals(
        recent_scores=[
            {
                "information_density": scored.information_density,
                "verbosity": scored.verbosity,
                "weak_phrase_count": scored.weak_phrase_count,
                "hashtag_count": scored.hashtag_count,
                "source": source,
            },
            *recent_rows,
        ],
        prior_daily=prior_daily,
    )
    fatigue_threshold = 0.45
    similarity_threshold = 0.62
    try:
        from bot.editorial.flow_health.adaptive import adaptive_modulation

        mod = adaptive_modulation()
        fatigue_threshold = float(mod.get("fatigue_threshold", fatigue_threshold))
        similarity_threshold = float(mod.get("quality_similarity_threshold", similarity_threshold))
    except Exception:
        pass
    warnings = build_quality_warnings(
        result=scored,
        headline=headline,
        summary=summary or "",
        tags=tags,
        source=source,
        template_key=tpl,
        hook_line=hook_line,
        recent=recent_rows,
        fatigue_threshold=fatigue_threshold,
        similarity_threshold=similarity_threshold,
    )
    dims = {
        "headline_strength": scored.dimensions.headline_strength,
        "summary_clarity": scored.dimensions.summary_clarity,
        "information_density": scored.dimensions.information_density,
        "redundancy": scored.dimensions.redundancy,
        "formatting_quality": scored.dimensions.formatting_quality,
        "hashtag_quality": scored.dimensions.hashtag_quality,
        "source_attribution_quality": scored.dimensions.source_attribution_quality,
        "cta_quality": scored.dimensions.cta_quality,
        "readability": scored.dimensions.readability,
        "style_alignment": scored.dimensions.style_alignment,
        "verbosity": scored.verbosity,
        "weak_phrase_count": scored.weak_phrase_count,
        "hashtag_count": scored.hashtag_count,
    }
    return EditorialQualityReport(
        editorial_quality_score=scored.editorial_quality_score,
        dimensions=dims,
        warnings=warnings,
        fatigue=fatigue,
        drift=drift,
        weak_phrases=scored.weak_phrases,
        template_key=tpl,
        metadata=scored.metadata,
    )


def evaluate_pending_item(
    item: Any,
    *,
    headline: str,
    summary: str | None,
    hook_line: str | None,
    repo: EditorialQualityRepository | None = None,
) -> EditorialQualityReport:
    recent = repo.recent_for_compare(exclude_pending_news_id=item.id) if repo else []
    prior = repo.load_daily_snapshots(limit=7) if repo else []
    return evaluate_post(
        headline=headline,
        summary=summary or "",
        link=item.link,
        tags=list(item.tags or []),
        source=item.source,
        hook_line=hook_line,
        recent=recent,
        prior_daily=prior,
    )
