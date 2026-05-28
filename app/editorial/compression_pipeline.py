"""End-to-end editorial compression: cluster → score → compress → render."""

from __future__ import annotations

from typing import Any

from app.editorial.clustering import cluster_items
from app.editorial.compression import CompressedCluster, compress_clusters
from app.editorial.dedup import collapse_topic_duplicates
from app.editorial.gatekeeper import editorial_gate, evaluate_editorial_gate, gate_filter_items
from app.editorial.ranking import score_item
from app.editorial.story_types import label_story_type
from app.publisher.draft_builder import render_hierarchical_draft
from utils.metrics import inc


def item_from_text(
    text: str,
    *,
    source: str = "",
    message_id: int | None = None,
    raw_id: int | None = None,
    runtime_dir: str | None = None,
    skip_gate: bool = False,
) -> dict[str, Any] | None:
    draft = {"text": text, "source": source, "message_id": message_id, "raw_id": raw_id}
    if not skip_gate and not editorial_gate(draft):
        return None
    rank = score_item({"text": text, "source": source}, runtime_dir=runtime_dir)
    item: dict[str, Any] = {
        "text": text,
        "source": source,
        "message_id": message_id,
        "raw_id": raw_id,
        "story_type": label_story_type(text, breaking_score=rank.breaking),
        "final_score": rank.final_score,
        "breaking": rank.breaking,
        "relevance": rank.relevance,
        "credibility": rank.credibility,
        "market_impact": rank.market_impact,
        "editorial_rank": rank.to_dict(),
    }
    if not skip_gate:
        from app.editorial.gatekeeper import apply_gate_boost

        item = apply_gate_boost(item, evaluate_editorial_gate(item))
    return item


def items_from_raw_posts(posts: list[Any], *, runtime_dir: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in posts:
        text = str(getattr(p, "text", None) or "")
        if not text.strip():
            continue
        row = item_from_text(
            text,
            source=str(getattr(p, "channel_name", None) or ""),
            message_id=int(getattr(p, "message_id", 0) or 0) or None,
            raw_id=int(getattr(p, "id", 0) or 0) or None,
            runtime_dir=runtime_dir,
        )
        if row is not None:
            out.append(row)
    return out


def parse_bullet_items(post_text: str, *, runtime_dir: str | None = None) -> list[dict[str, Any]]:
    """Parse • bullets from summarizer output into scored items."""
    items: list[dict[str, Any]] = []
    for line in (post_text or "").splitlines():
        s = line.strip()
        if not s.startswith("•"):
            continue
        body = s.lstrip("•").strip()
        if body.startswith("["):
            body = body.split("]", 1)[-1].strip()
        if len(body) < 20:
            continue
        row = item_from_text(body, runtime_dir=runtime_dir)
        if row is not None:
            items.append(row)
    return items


def run_compression_pipeline(
    items: list[dict[str, Any]],
    *,
    runtime_dir: str | None = None,
) -> tuple[list[CompressedCluster], str]:
    """
    cluster → dedup topics → compress → hierarchical render.
    Returns (kept clusters, html/plain body).
    """
    items = [it for it in items if isinstance(it, dict) and (it.get("text") or it.get("content"))]
    if not items:
        return [], "No items after compression."

    items = gate_filter_items(items, runtime_dir=runtime_dir, persist=True)
    if not items:
        return [], "No items passed editorial gate."

    for it in items:
        if "final_score" not in it:
            enriched = item_from_text(
                str(it.get("text") or ""),
                source=str(it.get("source") or ""),
                runtime_dir=runtime_dir,
            )
            it.update(enriched)

    collapsed = collapse_topic_duplicates(items)
    clusters = cluster_items(collapsed)
    kept = compress_clusters(clusters)

    dropped = max(0, len(items) - sum(len(c.items) for c in kept))
    if dropped:
        inc("compressed_items_dropped_total", dropped)
    inc("draft_clusters_kept_total", len(kept))

    body = render_hierarchical_draft(kept)
    return kept, body


def build_compressed_draft_from_posts(
    posts: list[Any],
    *,
    fallback_text: str = "",
    runtime_dir: str | None = None,
    max_chars: int = 2800,
) -> str:
    """Build hierarchical draft from raw posts (and optional summarizer bullets)."""
    if len(posts) == 1:
        from app.publisher.draft_builder import format_single_source_draft

        p = posts[0]
        return format_single_source_draft(
            {
                "text": str(getattr(p, "text", None) or ""),
                "source": str(getattr(p, "channel_name", None) or ""),
                "message_id": int(getattr(p, "message_id", 0) or 0) or None,
            },
            max_chars=max_chars,
            fallback_text=fallback_text,
        )

    items = items_from_raw_posts(posts, runtime_dir=runtime_dir)
    if len(items) < 2 and fallback_text:
        items.extend(parse_bullet_items(fallback_text, runtime_dir=runtime_dir))
    if not items and fallback_text:
        items = [item_from_text(fallback_text, runtime_dir=runtime_dir)]

    if len(items) == 1:
        from app.publisher.draft_builder import format_single_source_draft

        return format_single_source_draft(items[0], max_chars=max_chars, fallback_text=fallback_text)

    _, body = run_compression_pipeline(items, runtime_dir=runtime_dir)
    if len(body) > max_chars:
        body = body[: max_chars - 20].rstrip() + "\n…(truncated)"
    return body
