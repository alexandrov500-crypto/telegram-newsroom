from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.operator_console.explainability import (
    explain_story_compact,
    lineage_compact,
    why_flagged_compact,
)

if TYPE_CHECKING:
    from bot.epistemic.runtime import EpistemicIntegrityLayer
    from bot.storage.cluster_repository import ClusterRepository
    from bot.storage.editorial_repository import EditorialRepository


def explain_story(
    *,
    editorial: EditorialRepository,
    clusters: ClusterRepository | None,
    epistemic: EpistemicIntegrityLayer | None,
    news_id: int,
) -> str:
    return explain_story_compact(
        editorial=editorial,
        clusters=clusters,
        epistemic=epistemic,
        news_id=news_id,
    )


def story_lineage(
    *,
    editorial: EditorialRepository,
    news_id: int,
    node_id: str = "local",
) -> str:
    return lineage_compact(editorial=editorial, news_id=news_id, node_id=node_id)


def trust_story(
    *,
    epistemic: EpistemicIntegrityLayer | None,
    source: str | None,
) -> str:
    if epistemic is None or not source:
        return "Trust graph unavailable."
    edge = epistemic.trust.get_edge("mesh:local", f"source:{source}")
    score = edge.trust_score if edge else 0.5
    return f"<b>Trust {source}</b>\nScore {score:.2f}\n{edge.reason if edge else 'default'}"


def why_flagged(*, item: Any, assessment: Any | None = None) -> str:
    return why_flagged_compact(item=item, assessment=assessment)
