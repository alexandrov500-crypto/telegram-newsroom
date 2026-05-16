from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai.quality_score import compute_quality_scores, log_quality_scores
from app.config import Settings
from utils.observability import record_editorial_draft_sample
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def observe_draft_quality(
    logger: logging.Logger,
    settings: Settings,
    *,
    post_text: str,
    used_ids: list[int],
    sources_payload: list[dict[str, Any]],
    cluster_size: int,
    content_hash: str | None = None,
) -> None:
    """Heuristic warnings only — never blocks the pipeline."""
    t = (post_text or "").strip()
    if not t:
        log_event(logger, "quality.warn.empty_summary")
        return

    if len(t) < settings.quality_min_summary_chars:
        log_event(logger, "quality.warn.very_short_summary", chars=len(t), min_chars=settings.quality_min_summary_chars)

    words = re.findall(r"\w+", t.lower())
    if len(words) >= 40:
        uniq_ratio = len(set(words)) / len(words)
        if uniq_ratio < settings.quality_low_uniqueness_ratio:
            log_event(
                logger,
                "quality.warn.repetitive_summary",
                uniq_ratio=round(uniq_ratio, 3),
                threshold=settings.quality_low_uniqueness_ratio,
                word_count=len(words),
            )

    try:
        json.dumps(sources_payload)
    except TypeError:
        log_event(logger, "quality.warn.sources_not_json_serializable")
        return

    bad = 0
    seen_pairs: set[tuple[str, int]] = set()
    dup_rows = 0
    for item in sources_payload:
        if not isinstance(item, dict):
            bad += 1
            continue
        if "channel" not in item or "message_id" not in item:
            bad += 1
            continue
        ch = str(item.get("channel", "")).strip()
        if not ch:
            bad += 1
            continue
        try:
            mid = int(item["message_id"])
        except (TypeError, ValueError):
            bad += 1
            continue
        key = (ch, mid)
        if key in seen_pairs:
            dup_rows += 1
        else:
            seen_pairs.add(key)
    if bad:
        log_event(logger, "quality.warn.malformed_source_rows", bad_rows=bad, total_rows=len(sources_payload))
    if dup_rows:
        log_event(logger, "quality.warn.duplicate_source_rows", duplicate_rows=dup_rows, total_rows=len(sources_payload))

    used_n = len(used_ids)
    src_n = len(sources_payload)
    if used_n > 0 and src_n > 0 and used_n != src_n:
        log_event(
            logger,
            "quality.warn.source_count_mismatch",
            used_ids_count=used_n,
            sources_rows=src_n,
        )

    min_src = max(1, int(cluster_size * settings.quality_min_sources_ratio))
    if used_n < min_src and cluster_size >= settings.min_raw_posts_for_ai + 2:
        log_event(
            logger,
            "quality.warn.low_source_count",
            used=used_n,
            cluster_size=cluster_size,
            expected_at_least=min_src,
        )

    scores = compute_quality_scores(post_text=post_text, used_ids=used_ids, cluster_size=cluster_size)
    log_quality_scores(logger, scores, enabled=settings.quality_scoring_enabled)

    rep_raw = float(scores.get("repetition_raw") or 0.0)
    record_editorial_draft_sample(
        summary_len=len(t),
        source_count=src_n,
        content_hash=content_hash or "",
        repetition_bigram_ratio=rep_raw,
    )
