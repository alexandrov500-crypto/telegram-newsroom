"""W3 pre-publish enrichment pipeline."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from app.identity.differentiation import record_published_structure
from app.identity.identity_engine import evaluate_editorial_identity
from app.identity.insight_layer import extract_insight, score_insight_depth
from app.identity.opinion_layer import apply_light_framing
from app.identity.style_guide import detect_vertical, score_style_alignment
from app.flywheel.distribution_router import route_distribution_surface
from app.flywheel.explore_exploit import decide_explore_exploit
from app.flywheel.retention_habit import active_habit_slot


@dataclass(frozen=True)
class EnrichmentResult:
    content: str
    vertical: str
    insight_score: float
    style_score: float
    habit_hook: str


@dataclass(frozen=True)
class PrePublishVerdict:
    allowed: bool
    reason: str
    routing_reason: str
    insight_score: float
    style_score: float


def _enabled() -> bool:
    return os.getenv("W3_EDITORIAL_PIPELINE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def enrich_for_publish(
    body: str,
    *,
    vertical: str = "",
    runtime_dir: str = "",
    newsroom_tz: str = "Europe/Moscow",
    apply_opinion: bool = True,
) -> EnrichmentResult:
    if not _enabled():
        v = detect_vertical(body, vertical)
        return EnrichmentResult(body, v, score_insight_depth(body), 0.6, "")

    v = detect_vertical(body, vertical)
    insight = extract_insight(body, vertical=v)
    text = insight.text

    if apply_opinion and os.getenv("EDITORIAL_OPINION_LAYER_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        from app.editorial.reference_model import reference_model_enabled

        if not reference_model_enabled():
            frame = apply_light_framing(text, vertical=v)
            if frame.safe:
                text = frame.text

    slot = active_habit_slot(newsroom_tz)
    hook = ""
    if slot and slot.key != "weekly_synthesis":
        if slot.anticipation_hook.lower() not in text.lower()[:80]:
            hook = slot.anticipation_hook

    style = score_style_alignment(text, vertical=v)
    return EnrichmentResult(
        content=text,
        vertical=v,
        insight_score=insight.depth_score,
        style_score=style.score,
        habit_hook=hook,
    )


def evaluate_pre_publish_editorial(
    content: str,
    *,
    settings: object,
    runtime_dir: str,
    vertical: str = "",
    is_breaking: bool = False,
    novelty: float = 0.7,
    cohort_affinity: float = 0.35,
    signal_score: float = 0.55,
) -> PrePublishVerdict:
    identity = evaluate_editorial_identity(content, runtime_dir=runtime_dir, vertical=vertical)
    insight = score_insight_depth(content)
    style = identity.style_score

    if is_breaking:
        return PrePublishVerdict(True, "breaking_exempt", "breaking_lane", insight, style)

    explore = decide_explore_exploit(
        runtime_dir=runtime_dir,
        topic_bucket=vertical or "general",
        novelty=novelty,
        cohort_affinity=cohort_affinity,
    )

    route = route_distribution_surface(
        settings,
        is_breaking=False,
        insight_score=insight * explore.boost,
        style_score=style,
        signal_score=signal_score,
    )

    if route.surface.value == "discard" and explore.mode == "exploit":
        return PrePublishVerdict(False, "low_signal_routing", route.reason, insight, style)

    if not identity.allowed and explore.mode != "explore":
        return PrePublishVerdict(False, identity.reason, route.reason, insight, style)

    return PrePublishVerdict(True, "ok", route.reason, insight, style)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode()).hexdigest()[:20]
