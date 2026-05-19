from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.processing.semantic import build_fingerprint, jaccard_similarity


def record_duplicate_escape_event(
    *,
    pending_news_id: int,
    headline: str,
    cluster_id: int | None,
    source: str | None,
    context: dict[str, Any],
    slipped_through: bool = False,
) -> None:
    if not os.getenv("DUPLICATE_ESCAPE_LOG_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    try:
        from bot.storage.db import default_db_path, init_database

        path = init_database(default_db_path())
        with sqlite3.connect(path, timeout=5) as conn:
            conn.execute(
                """
                INSERT INTO ops_duplicate_escape_log (
                    pending_news_id, headline, cluster_id, source,
                    slipped_through, context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    headline[:300],
                    cluster_id,
                    (source or "")[:120],
                    1 if slipped_through else 0,
                    json.dumps(context, default=str),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
    except Exception:
        pass


def build_publish_context_snapshot() -> dict[str, Any]:
    """Forensic context at publish attempt — fail-open."""
    ctx: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.adaptive import adaptive_modulation
        from bot.editorial.flow_health.cadence import compute_cadence_health
        from bot.editorial.flow_health.floor import is_publish_floor_active
        from bot.editorial.flow_health.relaxation import effective_relaxation_scale
        from bot.editorial.flow_health.funnel import funnel_summary

        ctx["adaptive"] = adaptive_modulation()
        ctx["cadence"] = compute_cadence_health()
        ctx["floor_active"] = is_publish_floor_active()
        ctx["funnel"] = {
            "starvation": (funnel_summary().get("starvation") or {}),
        }
        ctx["relaxation"] = effective_relaxation_scale(
            starving=bool((ctx["funnel"]["starvation"] or {}).get("detected")),
            low_volume=False,
            overnight=False,
            burst=False,
        )
    except Exception as exc:
        ctx["error"] = str(exc)[:120]
    return ctx


def record_publish_forensics(
    *,
    pending_news_id: int,
    headline: str,
    cluster_id: int | None,
    source: str | None,
    tags: list[str] | None = None,
    published: bool = True,
) -> None:
    """Forensic snapshot on publish attempt/success — fail-open."""
    try:
        from bot.editorial.flow_health.diversity import compute_diversity_score

        div = compute_diversity_score(
            headline=headline,
            cluster_id=cluster_id,
            source=source,
            tags=tags,
        )
        ctx = build_publish_context_snapshot()
        ctx["diversity"] = div
        ctx["published"] = published
        slipped = published and (
            div.get("same_cluster_recent")
            or float(div.get("closest_similarity") or 0) >= float(div.get("max_allowed_similarity") or 1)
        )
        record_duplicate_escape_event(
            pending_news_id=pending_news_id,
            headline=headline,
            cluster_id=cluster_id,
            source=source,
            context=ctx,
            slipped_through=slipped,
        )
    except Exception:
        pass


def analyze_duplicate_slip(
    *,
    headline: str,
    cluster_id: int | None,
    source: str | None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Check if this publish duplicates recent content; record forensic event."""
    from bot.editorial.flow_health.diversity import compute_diversity_score

    div = compute_diversity_score(
        headline=headline,
        cluster_id=cluster_id,
        source=source,
    )
    ctx = build_publish_context_snapshot()
    ctx["diversity"] = div

    slipped = not div.get("publish_allowed", True)
    if slipped or div.get("closest_similarity", 0) >= 0.72:
        record_duplicate_escape_event(
            pending_news_id=0,
            headline=headline,
            cluster_id=cluster_id,
            source=source,
            context=ctx,
            slipped_through=slipped,
        )

    return {
        "slip_risk": slipped,
        "diversity": div,
        "context": ctx,
    }


def duplicate_escape_count(*, hours: int = 72, db_path: Path | None = None) -> int:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM ops_duplicate_escape_log
                WHERE created_at >= datetime('now', ?) AND slipped_through = 1
                """,
                (f"-{hours} hours",),
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.OperationalError:
        return 0
