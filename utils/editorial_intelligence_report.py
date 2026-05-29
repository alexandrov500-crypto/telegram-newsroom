"""Aggregated editorial intelligence for operator reports (JSON-friendly, explainable)."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from db.models import Draft
from db.session import close_db, init_db, session_scope
from editorial.drift_detection import evaluate_editorial_drift
from editorial.events import load_event_history
from editorial.feedback import collect_editorial_feedback_stats
from editorial.intelligence_store import cadence_state_path, entity_stats_path, load_json
from editorial.suppression_memory import duplicate_burst_count
from editorial.topic_memory import export_topic_snapshot
from editorial.trends import detect_topic_trends
from utils.metrics import export_snapshot


def _json_load(s: str) -> dict[str, Any]:
    try:
        o = json.loads(s or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return o if isinstance(o, dict) else {}


async def _collect_recent_draft_intel(session: AsyncSession, *, limit: int = 120) -> dict[str, Any]:
    stmt = select(Draft.id, Draft.status, Draft.draft_extras).order_by(Draft.id.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    rel_totals: list[float] = []
    conf_scores: list[float] = []
    hq_scores: list[float] = []
    suppressed_hint = 0
    status_counts: dict[str, int] = {}
    for _did, _st, extras_raw in rows:
        st_key = str(_st or "unknown")
        status_counts[st_key] = int(status_counts.get(st_key, 0)) + 1
        ex = _json_load(str(extras_raw or "{}"))
        ci = ex.get("cluster_intelligence") or {}
        if not isinstance(ci, dict):
            continue
        pd = ci.get("pipeline_decision") or {}
        if isinstance(pd, dict):
            rel = pd.get("relevance") or {}
            if isinstance(rel, dict) and rel.get("total") is not None:
                try:
                    rel_totals.append(float(rel["total"]))
                except (TypeError, ValueError):
                    pass
            if pd.get("suppress"):
                suppressed_hint += 1
        ec = ex.get("editorial_confidence") or {}
        if isinstance(ec, dict) and ec.get("confidence_score") is not None:
            try:
                conf_scores.append(float(ec["confidence_score"]))
            except (TypeError, ValueError):
                pass
        hq = ex.get("headline_quality") or {}
        if isinstance(hq, dict) and hq.get("score") is not None:
            try:
                hq_scores.append(float(hq["score"]))
            except (TypeError, ValueError):
                pass

    def _dist(vals: list[float], bins: tuple[float, ...]) -> dict[str, int]:
        out = {f"le_{b}": 0 for b in bins}
        out["other"] = 0
        for v in vals:
            placed = False
            for b in bins:
                if v <= b:
                    out[f"le_{b}"] += 1
                    placed = True
                    break
            if not placed:
                out["other"] += 1
        return out

    pending_total = 0
    try:
        pending_total = int(
            (
                await session.execute(
                    select(func.count()).select_from(Draft).where(Draft.status == "pending")
                )
            ).scalar_one()
            or 0
        )
    except Exception:
        pending_total = 0

    last_pub_created: str | None = None
    try:
        last_pub_created = (
            await session.scalar(
                select(Draft.created_at).where(Draft.status == "published").order_by(Draft.created_at.desc()).limit(1)
            )
        )
        if last_pub_created is not None:
            last_pub_created = str(last_pub_created)
    except Exception:
        last_pub_created = None

    return {
        "drafts_sampled": len(rows),
        "status_counts_sample": status_counts,
        "pending_backlog_total": pending_total,
        "last_published_created_at": last_pub_created,
        "cluster_intel_rows": len(rel_totals),
        "relevance_total_mean": round(statistics.mean(rel_totals), 3) if rel_totals else None,
        "relevance_total_median": round(statistics.median(rel_totals), 3) if rel_totals else None,
        "relevance_distribution": _dist(rel_totals, (25.0, 45.0, 65.0, 85.0)),
        "confidence_score_mean": round(statistics.mean(conf_scores), 4) if conf_scores else None,
        "headline_quality_mean": round(statistics.mean(hq_scores), 4) if hq_scores else None,
        "drafts_with_suppressed_pipeline_decision": suppressed_hint,
    }


def _asyncio_run_or_degrade(coro_factory):
    """
    Run ``asyncio.run(coro_factory())`` only when no event loop is running.
    When called from async code (e.g. dashboard bundle), skip and return None
    without leaving an un-awaited coroutine object.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    coro = coro_factory()
    coro.close()
    return None


def build_editorial_intelligence_report(settings: Settings) -> dict[str, Any]:
    """Sync entry: filesystem signals + metrics; DB slice via asyncio."""
    rd = settings.runtime_state_dir
    ctr = dict(export_snapshot().get("counters") or {})
    ent_blob = load_json(entity_stats_path(rd), {"version": 1, "entities": {}, "pairs": {}})
    ent_map = ent_blob.get("entities") or {}
    if not isinstance(ent_map, dict):
        ent_map = {}
    top_entities = sorted(((str(k), int(v)) for k, v in ent_map.items()), key=lambda kv: -kv[1])[:36]

    topics = export_topic_snapshot(rd, limit=48)
    trends = detect_topic_trends(rd)
    events = load_event_history(rd, limit=48)

    async def _db_slice() -> dict[str, Any]:
        await close_db()
        await init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        try:
            async with session_scope() as session:
                return await _collect_recent_draft_intel(session, limit=120)
        finally:
            await close_db()

    try:
        draft_intel = _asyncio_run_or_degrade(_db_slice)
        if draft_intel is None:
            draft_intel = {
                "drafts_sampled": 0,
                "cluster_intel_rows": 0,
                "drafts_with_suppressed_pipeline_decision": 0,
                "skipped_db_slice": True,
                "reason": "nested_event_loop",
            }
    except Exception as exc:  # noqa: BLE001 — report must degrade gracefully
        draft_intel = {"error": repr(exc)}

    async def _fb_slice() -> dict[str, Any] | None:
        await close_db()
        await init_db(
            settings.database_url,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        try:
            async with session_scope() as session:
                return await collect_editorial_feedback_stats(session)
        finally:
            await close_db()

    try:
        fb_stats = _asyncio_run_or_degrade(_fb_slice)
    except Exception:
        fb_stats = None

    di = draft_intel if isinstance(draft_intel, dict) else {}
    rows = int(di.get("cluster_intel_rows") or 0)
    sup_n = int(di.get("drafts_with_suppressed_pipeline_decision") or 0)
    sup_rate = round(sup_n / max(1, rows), 4) if rows else 0.0
    drift = evaluate_editorial_drift(
        rd,
        current_metrics={
            "suppression_rate": sup_rate,
            "avg_confidence": float(di.get("confidence_score_mean") or 0.0),
            "avg_headline_quality": float(di.get("headline_quality_mean") or 0.0),
            "manual_edit_rate": float(fb_stats.get("manual_edit_signals") or 0)
            / max(1, int(fb_stats.get("recent_drafts_sampled") or 1))
            if isinstance(fb_stats, dict)
            else 0.0,
        },
        current_feedback=fb_stats if isinstance(fb_stats, dict) else None,
        append_snapshot=True,
    )

    cad = load_json(cadence_state_path(rd), {"version": 1, "last_publish_unix": 0.0, "recent": []})
    try:
        from app.editorial.intelligence.operator_observability import build_operator_observability_snapshot

        op_obs = build_operator_observability_snapshot(rd)
    except Exception as exc:
        op_obs = {"error": repr(exc)}

    operational_diagnostics: dict[str, Any] = {}
    if isinstance(draft_intel, dict):
        pending_total = int(draft_intel.get("pending_backlog_total") or 0)
        last_pub_raw = draft_intel.get("last_published_created_at")
        minutes_since_publish: float | None = None
        if isinstance(last_pub_raw, str) and last_pub_raw.strip():
            try:
                dt = datetime.fromisoformat(last_pub_raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                minutes_since_publish = round((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0, 2)
            except Exception:
                minutes_since_publish = None
        operational_diagnostics = {
            "pending_backlog_total": pending_total,
            "minutes_since_last_published": minutes_since_publish,
            "publish_stall_risk": bool((minutes_since_publish or 0) >= 45 and pending_total >= 3),
            "recommended_operator_action": (
                "review_pending_queue_or_expand_fastlane_trusted_sources"
                if ((minutes_since_publish or 0) >= 45 and pending_total >= 3)
                else "normal"
            ),
        }

    return {
        "report": "editorial_intelligence",
        "schema_version": 1,
        "metrics": {
            "skipped_intelligence_suppress": int(ctr.get("skipped_intelligence_suppress", 0)),
            "cadence_deferred_cluster": int(ctr.get("cadence_deferred_cluster", 0)),
            "cadence_blocked_publish": int(ctr.get("cadence_blocked_publish", 0)),
            "skipped_duplicates": int(ctr.get("skipped_duplicates", 0)),
            "clusters_created": int(ctr.get("clusters_created", 0)),
            "drafts_created": int(ctr.get("drafts_created", 0)),
        },
        "topic_memory_top": topics[:24],
        "trend_signals": trends,
        "recent_event_history": events[:20],
        "top_entities": [{"normalized": n, "count": c} for n, c in top_entities],
        "draft_intelligence_from_db": draft_intel,
        "operator_observability": op_obs,
        "operational_diagnostics": operational_diagnostics,
        "cadence_recent": (cad.get("recent") or [])[:10],
        "duplicate_burst_count": duplicate_burst_count(rd),
        "editorial_drift": drift,
    }
