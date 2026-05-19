from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.operator_console.formatting import clamp_lines, escape

if TYPE_CHECKING:
    from bot.epistemic.runtime import EpistemicIntegrityLayer
    from bot.storage.cluster_repository import ClusterRepository
    from bot.storage.editorial_repository import EditorialRepository

MAX_EXPLAIN_LINES = 8


def explain_story_compact(
    *,
    editorial: EditorialRepository,
    clusters: ClusterRepository | None,
    epistemic: EpistemicIntegrityLayer | None,
    news_id: int,
) -> str:
    item = editorial.get_by_id(news_id)
    if item is None:
        return f"#{news_id}: not found."
    lines = [
        f"<b>#{news_id}</b> {escape(item.status)} · pri {item.priority_score:.2f}",
        f"Src {escape(item.source or '—')} · cluster {item.cluster_id or '—'}",
        f"Replay <code>evt_{news_id}</code>",
        escape(item.title[:160]),
    ]
    if item.summary:
        lines.append(escape(item.summary[:200]))
    if clusters is not None and item.cluster_id:
        view = clusters.get_cluster_view(item.cluster_id)
        lines.append(f"Evidence: {view.variant_count} variant(s) in cluster")
    if epistemic is not None:
        related = _linked_contradictions(epistemic, news_id, item.cluster_id)
        lines.append(
            f"Contradictions: {len(related)} open"
            if related
            else "Contradictions: none linked"
        )
    lines.append("→ /inspect_lineage " + str(news_id))
    return clamp_lines("\n".join(lines), max_lines=MAX_EXPLAIN_LINES)


def lineage_compact(
    *,
    editorial: EditorialRepository,
    news_id: int,
    node_id: str = "local",
) -> str:
    item = editorial.get_by_id(news_id)
    if item is None:
        return f"#{news_id}: not found."
    return clamp_lines(
        "\n".join(
            [
                f"<b>Lineage #{news_id}</b>",
                "ingest → enqueue → editorial",
                f"Node <code>{escape(node_id)}</code>",
                f"Cluster {item.cluster_id or 'none'}",
                f"Replay <code>evt_{news_id}</code>",
                f"Bundle <code>arch_evt_{news_id}</code>",
            ]
        ),
        max_lines=MAX_EXPLAIN_LINES,
    )


def why_flagged_compact(*, item: Any, assessment: Any | None = None) -> str:
    lines = [
        f"<b>Flagged #{item.id}</b> pri {item.priority_score:.2f}",
        f"Replay <code>evt_{item.id}</code>",
    ]
    if assessment is not None:
        lines.append(
            f"Risk {assessment.risk_score:.2f} · publish {assessment.publish_confidence:.2f}"
        )
        if assessment.requires_human_review:
            lines.append("Action: human review")
        blocked = assessment.blocked_categories or []
        if blocked:
            lines.append("Block: " + ", ".join(escape(str(c)) for c in blocked[:3]))
    else:
        lines.append("Action: awaiting risk score")
    return clamp_lines("\n".join(lines), max_lines=MAX_EXPLAIN_LINES)


def _linked_contradictions(
    epistemic: EpistemicIntegrityLayer,
    news_id: int,
    cluster_id: int | None,
) -> list[dict]:
    return [
        c
        for c in epistemic.contradictions.open_contradictions(limit=25)
        if str(c.get("subject_id", "")) == str(news_id)
        or str(c.get("cluster_id", "")) == str(cluster_id or "")
    ]
