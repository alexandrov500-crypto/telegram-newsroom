from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from bot.storage.db import default_db_path, init_database
from bot.trust_calibration.report import build_trust_calibration, build_trust_calibration_html
from bot.trust_calibration.repository import TrustCalibrationRepository

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("OPS_TRUST_CALIBRATION_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_trust_repo(db_path: Path | None = None) -> TrustCalibrationRepository:
    return TrustCalibrationRepository(init_database(db_path or default_db_path()))


def trust_calibration_html(*, db_path: Path | None = None) -> str:
    snap = build_trust_calibration(init_database(db_path or default_db_path()))
    return build_trust_calibration_html(snap)


def trust_calibration_payload(*, db_path: Path | None = None) -> dict[str, Any]:
    return build_trust_calibration(init_database(db_path or default_db_path()))


def _enrich_trace_from_tables(path: Path, pending_news_id: int, trace: dict) -> dict:
    import json
    import sqlite3

    out = dict(trace)
    try:
        with sqlite3.connect(path, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            q = conn.execute(
                """
                SELECT editorial_quality_score, warnings_json FROM editorial_quality_scores
                WHERE pending_news_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (pending_news_id,),
            ).fetchone()
            if q:
                out.setdefault("editorial_quality_score", q["editorial_quality_score"])
                try:
                    warns = json.loads(q["warnings_json"] or "[]")
                    eq = out.setdefault("editorial_quality", {})
                    if isinstance(eq, dict):
                        eq.setdefault("warnings", warns)
                except json.JSONDecodeError:
                    pass
            p = conn.execute(
                """
                SELECT editorial_priority_score, warnings_json, factors_json
                FROM editorial_priority_scores WHERE pending_news_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (pending_news_id,),
            ).fetchone()
            if p:
                out.setdefault("editorial_priority_score", p["editorial_priority_score"])
                try:
                    warns = json.loads(p["warnings_json"] or "[]")
                    ep = out.setdefault("editorial_priority", {})
                    if isinstance(ep, dict):
                        ep.setdefault("warnings", warns)
                except json.JSONDecodeError:
                    pass
    except sqlite3.OperationalError:
        pass
    return out


def record_from_publish_trace(pending_news_id: int, *, db_path: Path | None = None) -> None:
    """Snapshot subsystem signals at publish time for later agreement analysis."""
    if not _enabled():
        return
    try:
        from bot.live_ops.publish_trace import PublishTraceStore

        path = init_database(db_path or default_db_path())
        trace = _enrich_trace_from_tables(path, pending_news_id, PublishTraceStore(path).get(pending_news_id) or {})
        repo = TrustCalibrationRepository(path)

        eq = trace.get("editorial_quality") or {}
        if isinstance(eq, dict):
            for w in eq.get("warnings") or []:
                repo.record_event(
                    pending_news_id=pending_news_id,
                    subsystem="editorial_quality",
                    signal_type="quality_warning",
                    signal_value=str(w)[:120],
                    operator_action="pending",
                    outcome="published",
                )
            score = trace.get("editorial_quality_score")
            if score is not None:
                repo.record_event(
                    pending_news_id=pending_news_id,
                    subsystem="editorial_quality",
                    signal_type="quality_score",
                    signal_value=str(score),
                    outcome="published",
                )

        em = trace.get("editorial_memory") or {}
        if isinstance(em, dict):
            for w in em.get("warnings") or []:
                sub = "contradiction_detection" if "contradict" in str(w).lower() else "memory_matching"
                repo.record_event(
                    pending_news_id=pending_news_id,
                    subsystem=sub,
                    signal_type="memory_warning",
                    signal_value=str(w)[:120],
                    operator_action="pending",
                )

        pri = float(trace.get("editorial_priority_score") or 0)
        if pri >= 0.68:
            repo.record_event(
                pending_news_id=pending_news_id,
                subsystem="prioritization",
                signal_type="priority_score_high",
                signal_value=f"{pri:.3f}",
                outcome="published",
            )
        ep = trace.get("editorial_priority") or {}
        if isinstance(ep, dict):
            for w in ep.get("warnings") or []:
                repo.record_event(
                    pending_news_id=pending_news_id,
                    subsystem="prioritization",
                    signal_type="priority_warning",
                    signal_value=str(w)[:120],
                    operator_action="pending",
                )
    except Exception:
        logger.debug("event=trust_record_publish_failed id=%s", pending_news_id)


def record_operator_rating(
    *,
    pending_news_id: int,
    good: bool,
    operator_id: int | None = None,
    db_path: Path | None = None,
) -> None:
    if not _enabled():
        return
    try:
        repo = get_trust_repo(db_path)
        outcome = "operator_mark_good" if good else "operator_mark_bad"
        action = "confirmed" if good else "override"
        for sub in ("editorial_quality", "prioritization", "memory_matching", "fatigue_detection"):
            repo.record_event(
                pending_news_id=pending_news_id,
                subsystem=sub,
                signal_type=outcome,
                operator_action=action,
                outcome=outcome,
                detail={"operator_id": operator_id},
            )
        _reconcile_rating(repo, pending_news_id, good=good)
    except Exception:
        logger.debug("event=trust_record_rating_failed id=%s", pending_news_id)


def _reconcile_rating(repo: TrustCalibrationRepository, pending_news_id: int, *, good: bool) -> None:
    from bot.live_ops.publish_trace import PublishTraceStore
    from bot.trust_calibration.agreement import _warnings_from_trace

    path = repo._db_path
    trace = _enrich_trace_from_tables(
        path,
        pending_news_id,
        PublishTraceStore(path).get(pending_news_id) or {},
    )
    warnings = _warnings_from_trace(trace)
    for sub, warns in warnings.items():
        if not warns:
            continue
        repo.record_event(
            pending_news_id=pending_news_id,
            subsystem=sub,
            signal_type="warning_outcome",
            operator_action="ignored" if good else "confirmed",
            outcome="false_positive" if good else "true_positive",
            detail={"warnings": warns[:3]},
        )


def schedule_publish_trust_record(pending_news_id: int) -> None:
    async def _run() -> None:
        await asyncio.sleep(3.0)
        await asyncio.to_thread(record_from_publish_trace, pending_news_id)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        record_from_publish_trace(pending_news_id)
