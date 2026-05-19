from __future__ import annotations

import math
from datetime import datetime, timezone

from bot.editorial.story_types import StoryMatchCandidate, StorySnapshot
from bot.processing.semantic import build_fingerprint, jaccard_similarity, storage_to_tokens


MATCH_THRESHOLD = 0.52
STRONG_MATCH_THRESHOLD = 0.68


def _parse_iso(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def recency_score(last_updated_at: str, *, half_life_hours: float = 36.0) -> float:
    """Exponential decay; 1.0 when just updated."""
    now = datetime.now(timezone.utc)
    then = _parse_iso(last_updated_at)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    hours = max(0.0, (now - then).total_seconds() / 3600.0)
    return math.exp(-hours / half_life_hours)


def entity_overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def embedding_similarity_for_text(
    title: str,
    *,
    fingerprint_storage: str | None,
) -> tuple[set[str], float]:
    tokens, _ = build_fingerprint(title)
    if not fingerprint_storage:
        return tokens, 0.0
    stored = storage_to_tokens(fingerprint_storage)
    return tokens, jaccard_similarity(tokens, stored)


def score_story_match(
    *,
    title: str,
    entity_keys: set[str],
    candidate: StorySnapshot,
    candidate_entity_keys: set[str] | None = None,
) -> StoryMatchCandidate:
    fingerprint, emb_sim = embedding_similarity_for_text(
        title,
        fingerprint_storage=candidate.fingerprint_storage,
    )
    _ = fingerprint
    ent_sim = entity_overlap_score(
        entity_keys,
        candidate_entity_keys or set(candidate.entity_names),
    )
    recency = recency_score(candidate.last_updated_at)
    return StoryMatchCandidate(
        story=candidate,
        embedding_similarity=emb_sim,
        entity_overlap=ent_sim,
        recency_score=recency,
    )


def pick_best_story_match(
    *,
    title: str,
    entity_keys: set[str],
    candidates: list[StorySnapshot],
    entity_map: dict[int, set[str]] | None = None,
) -> tuple[StorySnapshot | None, float]:
    """Return best matching story and score, or None if below threshold."""
    if not candidates:
        return None, 0.0
    best: StoryMatchCandidate | None = None
    for story in candidates:
        keys = (entity_map or {}).get(story.id, set(story.entity_names))
        scored = score_story_match(
            title=title,
            entity_keys=entity_keys,
            candidate=story,
            candidate_entity_keys=keys,
        )
        if best is None or scored.match_score > best.match_score:
            best = scored
    if best is None or best.match_score < MATCH_THRESHOLD:
        return None, best.match_score if best else 0.0
    return best.story, best.match_score
