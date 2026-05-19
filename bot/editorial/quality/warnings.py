from __future__ import annotations

from bot.editorial.quality.fatigue import compute_fatigue_metrics
from bot.editorial.quality.phrases import find_weak_phrases, opening_trigram, phrase_hits_in_corpus
from bot.editorial.quality.scoring import EditorialQualityResult
from bot.editorial.quality.similarity import find_similar_posts
from bot.editorial.quality.style_profile import DEFAULT_STYLE


def build_quality_warnings(
    *,
    result: EditorialQualityResult,
    headline: str,
    summary: str,
    tags: list[str],
    source: str | None,
    template_key: str,
    hook_line: str | None,
    recent: list[dict],
    phrase_corpus: list[str] | None = None,
    fatigue_threshold: float = 0.45,
    similarity_threshold: float = 0.62,
) -> tuple[str, ...]:
    warnings: list[str] = []
    corpus = phrase_corpus or [str(r.get("headline") or "") + " " + str(r.get("summary") or "") for r in recent]

    for phrase in result.weak_phrases[:3]:
        if phrase_hits_in_corpus(phrase, corpus) >= 2:
            warnings.append(f"repetitive phrasing: {phrase}")
        else:
            warnings.append(f"weak phrasing: {phrase}")

    if result.dimensions.headline_strength < 0.5:
        warnings.append("weak headline")

    if result.hashtag_count > DEFAULT_STYLE.max_hashtags:
        warnings.append("excessive hashtags")
    elif result.hashtag_count == 0 and len(tags) > 0:
        warnings.append("hashtag normalization issue")

    if result.information_density < 0.42:
        warnings.append("low information density")

    if result.dimensions.summary_clarity < 0.5:
        warnings.append("summary too thin or verbose")

    matches = find_similar_posts(
        headline=headline,
        summary=summary,
        tags=tags,
        recent=recent,
        threshold=similarity_threshold,
    )
    if matches:
        best = max(matches, key=lambda m: m.score)
        warnings.append(f"similar to recent post #{best.pending_news_id} ({best.field})")

    opener = opening_trigram(headline)
    if opener and sum(1 for r in recent if opening_trigram(str(r.get("headline") or "")) == opener) >= 2:
        warnings.append("repetitive headline opening")

    fatigue = compute_fatigue_metrics(
        source=source,
        template_key=template_key,
        tags=tags,
        tone_marker=hook_line or opener,
        recent=recent,
    )
    if fatigue["topic_fatigue"] >= fatigue_threshold:
        warnings.append("topic fatigue — similar tags recently")
    if fatigue["source_fatigue"] >= fatigue_threshold:
        warnings.append("source fatigue — same outlet pacing")
    if fatigue["template_fatigue"] >= fatigue_threshold:
        warnings.append("template fatigue — format overuse")
    if fatigue["tone_fatigue"] >= fatigue_threshold:
        warnings.append("tone fatigue — repeated hooks/openers")

    # Dedupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for w in warnings:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(w)
    return tuple(unique[:8])
