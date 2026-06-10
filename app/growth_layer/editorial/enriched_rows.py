"""Merge validation metrics with editorial features for pattern analysis."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.validation.status import filter_final_rows
from db.editorial_features_repository import list_post_editorial_features
from db.growth_validation_repository import list_post_growth_validation


async def load_enriched_validation_rows(
    session: AsyncSession,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """FINAL validation rows enriched with editorial feature snapshots."""
    validation_rows = await list_post_growth_validation(session, limit=limit, final_only=True)
    final_rows = filter_final_rows(validation_rows)
    if not final_rows:
        return []
    draft_ids = [int(r["draft_id"]) for r in final_rows if r.get("draft_id") is not None]
    feature_rows = await list_post_editorial_features(session, draft_ids=draft_ids)
    by_draft = {int(f["draft_id"]): f for f in feature_rows}
    enriched: list[dict[str, Any]] = []
    for row in final_rows:
        draft_id = int(row.get("draft_id") or 0)
        merged = dict(row)
        feats = by_draft.get(draft_id)
        if feats:
            merged.update(feats)
        enriched.append(merged)
    return enriched
