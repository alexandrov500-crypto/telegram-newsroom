from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.processing.semantic import build_fingerprint, jaccard_similarity


def _min_story_distance() -> float:
    try:
        return float(os.getenv("MIN_STORY_DISTANCE_FOR_FLOOR", "0.35"))
    except ValueError:
        return 0.35


def _max_similarity_allowed() -> float:
    """Stories more similar than this to a recent publish are blocked under floor."""
    return max(0.5, 1.0 - _min_story_distance())


def _recent_published_titles(*, hours: int = 6, db_path: Path | None = None) -> list[str]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    titles: list[str] = []
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            for table, col in (
                ("published_posts", "title"),
                ("editorial_quality_scores", "headline"),
            ):
                try:
                    rows = conn.execute(
                        f"""
                        SELECT {col} AS t FROM {table}
                        WHERE created_at >= datetime('now', ?)
                           OR published_at >= datetime('now', ?)
                        ORDER BY rowid DESC LIMIT 30
                        """,
                        (f"-{hours} hours", f"-{hours} hours"),
                    ).fetchall()
                    titles.extend(str(r["t"]) for r in rows if r["t"])
                except sqlite3.OperationalError:
                    try:
                        rows = conn.execute(
                            f"""
                            SELECT {col} AS t FROM {table}
                            WHERE created_at >= datetime('now', ?)
                            ORDER BY created_at DESC LIMIT 30
                            """,
                            (f"-{hours} hours",),
                        ).fetchall()
                        titles.extend(str(r["t"]) for r in rows if r["t"])
                    except sqlite3.OperationalError:
                        pass
    except Exception:
        pass
    return titles[:40]


def _cluster_recently_published(
    cluster_id: int | None, *, hours: int = 24, db_path: Path | None = None
) -> bool:
    if cluster_id is None:
        return False
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM published_posts
                WHERE cluster_id = ? AND published_at >= datetime('now', ?)
                LIMIT 1
                """,
                (cluster_id, f"-{hours} hours"),
            ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False


def _recent_publish_meta(*, hours: int = 6, db_path: Path | None = None) -> list[dict]:
    from bot.storage.db import default_db_path, init_database

    path = init_database(db_path or default_db_path())
    out: list[dict] = []
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT p.cluster_id, p.headline, p.topics_json, pn.source AS news_source
                FROM published_posts p
                LEFT JOIN pending_news pn ON pn.id = p.pending_news_id
                WHERE p.published_at >= datetime('now', ?)
                ORDER BY p.published_at DESC LIMIT 25
                """,
                (f"-{hours} hours",),
            ).fetchall()
            for row in rows:
                out.append(
                    {
                        "cluster_id": row["cluster_id"],
                        "headline": row["headline"] or "",
                        "topics_json": row["topics_json"],
                        "source": row["news_source"],
                    }
                )
    except sqlite3.OperationalError:
        pass
    return out


def compute_diversity_score(
    *,
    headline: str,
    cluster_id: int | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
    hours: int = 6,
    db_path: Path | None = None,
) -> dict:
    """
    Heuristic diversity (0–1) from cluster distance, source/topic spread.
    Used for floor recovery and publish gates — no embeddings.
    """
    try:
        fp, _ = build_fingerprint(headline)
        max_sim = _max_similarity_allowed()
        closest = 0.0
        same_cluster = _cluster_recently_published(cluster_id, hours=24, db_path=db_path)
        recent_sources: list[str] = []
        recent_tags: set[str] = set()

        for meta in _recent_publish_meta(hours=hours, db_path=db_path):
            if meta.get("cluster_id") == cluster_id and cluster_id is not None:
                same_cluster = True
            title = meta.get("headline") or ""
            if title:
                other_fp, _ = build_fingerprint(title)
                closest = max(closest, jaccard_similarity(fp, other_fp))
            try:
                import json

                for t in json.loads(meta.get("topics_json") or "[]")[:8]:
                    recent_tags.add(str(t).lower()[:40])
            except (json.JSONDecodeError, TypeError):
                pass

        title_component = 1.0 - min(1.0, closest / max(max_sim, 0.01))
        cluster_component = 0.0 if same_cluster else 1.0
        source_component = 1.0
        if source:
            src = source.strip().lower()[:80]
            for meta in _recent_publish_meta(hours=hours, db_path=db_path):
                prev = (meta.get("source") or "").strip().lower()[:80]
                if prev and prev == src:
                    source_component = 0.35
                    break
        tag_component = 1.0
        if tags:
            overlap = sum(1 for t in tags if str(t).lower()[:40] in recent_tags)
            if overlap >= 2 and len(recent_tags) >= 2:
                tag_component = 0.4

        diversity_score = round(
            title_component * 0.45
            + cluster_component * 0.30
            + source_component * 0.15
            + tag_component * 0.10,
            3,
        )
        min_distance = _min_story_distance()
        publish_allowed = (
            not same_cluster
            and closest < max_sim
            and diversity_score >= min_distance
        )
        return {
            "diversity_score": diversity_score,
            "closest_similarity": round(closest, 3),
            "max_allowed_similarity": round(max_sim, 3),
            "same_cluster_recent": same_cluster,
            "publish_allowed": publish_allowed,
            "min_story_distance": min_distance,
        }
    except Exception:
        return {
            "diversity_score": 1.0,
            "publish_allowed": True,
            "reason": "diversity_compute_failed_open",
        }


def publish_diversity_gate(
    *,
    headline: str,
    cluster_id: int | None = None,
    source: str | None = None,
    tags: list[str] | None = None,
    floor_only: bool = False,
) -> dict:
    """
    Publish-time diversity protection (always-on unless disabled).
    floor_only: when true, only enforced during publish floor (recovery).
    """
    if not os.getenv("PUBLISH_DIVERSITY_GATE_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"allowed": True, "reason": "gate_disabled"}

    if floor_only:
        from bot.editorial.flow_health.floor import is_publish_floor_active

        if not is_publish_floor_active():
            return {"allowed": True, "reason": "floor_inactive"}

    score = compute_diversity_score(
        headline=headline,
        cluster_id=cluster_id,
        source=source,
        tags=tags,
    )
    if score.get("publish_allowed", True):
        return {"allowed": True, "diversity": score}
    reason = "same_cluster_recent" if score.get("same_cluster_recent") else "insufficient_story_distance"
    return {"allowed": False, "reason": reason, "diversity": score}


def floor_diversity_allows(headline: str, *, hours: int = 6, db_path: Path | None = None) -> dict:
    """
    During floor recovery, block near-duplicate wire rewrites (not strict dedupe).
    Fail-open: allows on error.
    """
    if not os.getenv("PUBLISH_FLOOR_DIVERSITY_ENABLED", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"allowed": True, "reason": "diversity_check_disabled"}

    gate = publish_diversity_gate(headline=headline, floor_only=True)
    div = gate.get("diversity") or {}
    if gate.get("allowed", True):
        return {
            "allowed": True,
            "closest_similarity": div.get("closest_similarity", 0),
            "max_allowed_similarity": div.get("max_allowed_similarity"),
            "diversity_score": div.get("diversity_score"),
        }
    return {
        "allowed": False,
        "reason": gate.get("reason", "insufficient_story_distance"),
        "closest_similarity": div.get("closest_similarity"),
        "max_allowed_similarity": div.get("max_allowed_similarity"),
        "diversity_score": div.get("diversity_score"),
    }
