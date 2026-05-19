from __future__ import annotations

from bot.editorial.memory.types import StorylineSnapshot
from bot.editorial.quality.phrases import jaccard_similarity
from bot.editorial.memory.topics import extract_entity_keys, extract_topic_keys, primary_storyline_slug, storyline_id_from_slug


def score_storyline_match(
    *,
    headline: str,
    summary: str | None,
    tags: list[str],
    candidate: StorylineSnapshot,
) -> float:
    topic_keys = set(extract_topic_keys(headline, summary or "", tags=tags))
    cand_topics = set(candidate.topic_keys)
    topic_score = len(topic_keys & cand_topics) / max(1, len(topic_keys | cand_topics))

    entities = set(k.lower() for k in extract_entity_keys(headline, summary))
    cand_entities = set(k.lower() for k in candidate.entity_keys)
    entity_score = len(entities & cand_entities) / max(1, len(entities | cand_entities))

    text_score = jaccard_similarity(
        headline,
        candidate.latest_headline or candidate.title,
    )
    if summary and candidate.latest_summary:
        text_score = max(text_score, jaccard_similarity(summary, candidate.latest_summary) * 0.9)

    return round(topic_score * 0.45 + entity_score * 0.25 + text_score * 0.3, 3)


def pick_storyline(
    *,
    headline: str,
    summary: str | None,
    tags: list[str],
    candidates: list[StorylineSnapshot],
    threshold: float = 0.38,
) -> tuple[StorylineSnapshot | None, float, str]:
    topic_keys = extract_topic_keys(headline, summary or "", tags=tags)
    slug = primary_storyline_slug(topic_keys)
    default_id = storyline_id_from_slug(slug)

    best: StorylineSnapshot | None = None
    best_score = 0.0
    for cand in candidates:
        score = score_storyline_match(
            headline=headline,
            summary=summary,
            tags=tags,
            candidate=cand,
        )
        if score > best_score:
            best_score = score
            best = cand

    if best is not None and best_score >= threshold:
        return best, best_score, best.storyline_id

    for cand in candidates:
        if cand.storyline_id == default_id:
            return cand, max(best_score, 0.4), default_id

    return None, best_score, default_id
