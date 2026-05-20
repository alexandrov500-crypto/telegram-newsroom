"""Fail-open editorial scoring enrichment for drafts."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import RawPost
from editorial.scoring.explainability import build_explainability_reasons
from editorial.scoring.models import EditorialIntelligenceScores, ScoringInput
from editorial.scoring.novelty import compute_novelty_score
from editorial.scoring.priority import (
    compute_cluster_importance_score,
    compute_duplicate_confidence,
    compute_publish_priority_score,
)
from editorial.scoring.quality import compute_quality_score
from editorial.scoring.trust import compute_source_trust_score
from editorial.scoring.base import level_label
from utils.source_reputation import export_channel_scores_for_priority
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

DEFAULT_SCORING_TIMEOUT_SEC = 2.0


def _channel_trust_map(
    sources_payload: list[dict[str, object]],
    reputation: dict[str, float],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in sources_payload:
        if not isinstance(s, dict):
            continue
        ch = str(s.get("channel") or "").strip().lower()
        if not ch:
            continue
        out[ch] = float(reputation.get(ch, reputation.get(ch.lstrip("@"), 0.5)))
    return out


def compute_editorial_intelligence(inp: ScoringInput) -> EditorialIntelligenceScores:
    quality = compute_quality_score(inp.quality_scores)
    novelty = compute_novelty_score(
        quality_scores=inp.quality_scores,
        duplicate_intel=inp.duplicate_intel,
    )
    trust = compute_source_trust_score(inp.source_trust_by_channel)
    dup_conf = compute_duplicate_confidence(
        duplicate_intel=inp.duplicate_intel,
        editorial_scores_card=inp.editorial_scores_card,
    )
    cluster_imp = compute_cluster_importance_score(
        cluster_size=inp.cluster_size,
        unique_channel_count=inp.unique_channel_count,
        source_convergence=inp.source_convergence,
    )
    pub_score = compute_publish_priority_score(
        publication_priority=inp.publication_priority,
        editorial_priority=inp.editorial_priority,
        cluster_importance=cluster_imp,
        quality_score=quality,
    )
    label = level_label(pub_score, high=0.72, medium=0.45).upper()
    draft = EditorialIntelligenceScores(
        quality_score=quality,
        novelty_score=novelty,
        source_trust_score=trust,
        duplicate_confidence=dup_conf,
        cluster_importance_score=cluster_imp,
        publish_priority_score=pub_score,
        operator_feedback_score=None,
        publish_priority_label=label,
    )
    draft.reasons = build_explainability_reasons(inp, draft)
    return draft


def _build_input(
    *,
    draft_id: int,
    draft_text: str,
    used_posts: list[RawPost],
    cluster_size: int,
    sources_payload: list[dict[str, object]],
    quality_scores: dict[str, Any],
    duplicate_intel: dict[str, Any],
    editorial_scores_card: dict[str, float],
    publication_priority: dict[str, Any] | None,
    editorial_priority: dict[str, Any] | None,
    runtime_dir: str,
    source_convergence: float,
) -> ScoringInput:
    rep = export_channel_scores_for_priority(runtime_dir)
    chans = {
        str(p.channel_name).strip().lower()
        for p in used_posts
        if str(p.channel_name).strip()
    }
    return ScoringInput(
        draft_id=draft_id,
        draft_text=draft_text,
        cluster_size=cluster_size,
        source_count=len(sources_payload),
        unique_channel_count=len(chans),
        quality_scores=quality_scores,
        duplicate_intel=duplicate_intel,
        editorial_scores_card=editorial_scores_card,
        publication_priority=publication_priority,
        editorial_priority=editorial_priority,
        source_trust_by_channel=_channel_trust_map(sources_payload, rep),
        source_convergence=source_convergence,
    )


def _record_metrics(scores: EditorialIntelligenceScores) -> None:
    from editorial.scoring.metrics import record_scoring_success

    record_scoring_success(scores)


async def enrich_draft_editorial_intelligence(
    session: AsyncSession,
    *,
    draft_id: int,
    draft_text: str,
    used_posts: list[RawPost],
    cluster_size: int,
    sources_payload: list[dict[str, object]],
    quality_scores: dict[str, Any],
    duplicate_intel: dict[str, Any],
    editorial_scores_card: dict[str, float],
    publication_priority: dict[str, Any] | None,
    editorial_priority: dict[str, Any] | None,
    runtime_dir: str,
    source_convergence: float = 0.0,
    timeout_sec: float = DEFAULT_SCORING_TIMEOUT_SEC,
    enabled: bool = True,
) -> dict[str, Any] | None:
    """
    Compute explainable scores, persist ``editorial_scores`` row, return extras payload.
    Fail-open: never raises to caller.
    """
    if not enabled:
        return None

    t0 = time.perf_counter()
    log_event(logger, "editorial.scoring.started", draft_id=draft_id, timeout_sec=timeout_sec)

    try:
        inp = _build_input(
            draft_id=draft_id,
            draft_text=draft_text,
            used_posts=used_posts,
            cluster_size=cluster_size,
            sources_payload=sources_payload,
            quality_scores=quality_scores,
            duplicate_intel=duplicate_intel,
            editorial_scores_card=editorial_scores_card,
            publication_priority=publication_priority,
            editorial_priority=editorial_priority,
            runtime_dir=runtime_dir,
            source_convergence=source_convergence,
        )

        async def _compute_and_persist() -> dict[str, Any]:
            scores = await asyncio.to_thread(compute_editorial_intelligence, inp)
            from db.editorial_scores_repository import upsert_editorial_scores

            await upsert_editorial_scores(session, scores.to_db_row(draft_id=draft_id))
            return scores.to_extras_payload()

        payload = await asyncio.wait_for(_compute_and_persist(), timeout=timeout_sec)
        _record_metrics(
            EditorialIntelligenceScores(
                quality_score=float(payload["quality_score"]),
                novelty_score=float(payload["novelty_score"]),
                source_trust_score=float(payload["source_trust_score"]),
                duplicate_confidence=float(payload["duplicate_confidence"]),
                cluster_importance_score=float(payload["cluster_importance_score"]),
                publish_priority_score=float(payload["publish_priority_score"]),
                publish_priority_label=str(payload.get("publish_priority") or "MEDIUM"),
                reasons=list(payload.get("reasons") or []),
            )
        )
        log_event(
            logger,
            "editorial.scoring.completed",
            draft_id=draft_id,
            duration_sec=round(time.perf_counter() - t0, 4),
            quality_score=payload.get("quality_score"),
            novelty_score=payload.get("novelty_score"),
            publish_priority=payload.get("publish_priority"),
            reason_count=len(payload.get("reasons") or []),
        )
        return payload
    except asyncio.TimeoutError:
        from editorial.scoring.metrics import record_scoring_failure

        record_scoring_failure()
        log_event(
            logger,
            "editorial.scoring.failed",
            draft_id=draft_id,
            duration_sec=round(time.perf_counter() - t0, 4),
            error="timeout",
            recovery="fail_open_skip",
        )
        return None
    except Exception as exc:
        from editorial.scoring.metrics import record_scoring_failure

        record_scoring_failure()
        log_event(
            logger,
            "editorial.scoring.failed",
            draft_id=draft_id,
            duration_sec=round(time.perf_counter() - t0, 4),
            error=repr(exc)[:500],
            recovery="fail_open_skip",
        )
        return None
