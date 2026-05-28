"""Post-launch quality stability monitor (warning-only)."""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def _report_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "post_quality_report.json"


def _safe_load_json(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def _topic_hint(extras: dict[str, Any]) -> str:
    ci = extras.get("cluster_intelligence") if isinstance(extras, dict) else {}
    if isinstance(ci, dict):
        ident = ci.get("event_identity") if isinstance(ci.get("event_identity"), dict) else {}
        return str(ident.get("topic_hint") or ci.get("topic_hint") or "").strip().lower()
    return ""


def _quality_score_from_counts(c: dict[str, int]) -> float:
    penalties = (
        c.get("duplicate_like_publishes", 0) * 8
        + c.get("malformed_formatting", 0) * 6
        + c.get("empty_or_short_publishes", 0) * 10
        + c.get("repeated_topic_bursts", 0) * 5
        + c.get("language_inconsistency", 0) * 4
        + c.get("failed_media_attachments", 0) * 6
        + c.get("retry_generated_drafts", 0) * 4
        + c.get("operator_rejection_spikes", 0) * 5
    )
    return round(max(0.0, 100.0 - penalties), 1)


def build_post_quality_report(conn: sqlite3.Connection, *, runtime_dir: str) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT d.id, d.content, d.sources, d.draft_extras, pp.published_at
        FROM published_posts pp
        JOIN drafts d ON d.id = pp.draft_id
        WHERE pp.published_at >= datetime('now', '-24 hours')
        ORDER BY pp.id DESC
        """
    ).fetchall()
    counts: dict[str, int] = {
        "duplicate_like_publishes": 0,
        "malformed_formatting": 0,
        "empty_or_short_publishes": 0,
        "repeated_topic_bursts": 0,
        "language_inconsistency": 0,
        "failed_media_attachments": 0,
        "retry_generated_drafts": 0,
        "operator_rejection_spikes": 0,
    }
    topic_counter: Counter[str] = Counter()
    lang_counter: Counter[str] = Counter()
    for _, content, _sources, extras_raw, _ in rows:
        txt = str(content or "")
        ex = _safe_load_json(str(extras_raw or "{}"))
        if len(txt.strip()) < int(os.getenv("POST_QUALITY_MIN_CHARS", "80")):
            counts["empty_or_short_publishes"] += 1
        if txt.count("{") + txt.count("```") > 1 or ("<b>" in txt and "</b>" not in txt):
            counts["malformed_formatting"] += 1
        dup = ex.get("duplicate_intel") if isinstance(ex, dict) else {}
        try:
            if isinstance(dup, dict) and float(dup.get("max_similarity_pct") or 0) >= 85.0:
                counts["duplicate_like_publishes"] += 1
        except (TypeError, ValueError):
            pass
        media = ex.get("media") if isinstance(ex, dict) else {}
        if isinstance(media, dict) and str(media.get("status") or "").lower() in {"failed", "error"}:
            counts["failed_media_attachments"] += 1
        ai_gen = ex.get("ai_generation") if isinstance(ex, dict) else {}
        if isinstance(ai_gen, dict) and str(ai_gen.get("path") or "").startswith("retry"):
            counts["retry_generated_drafts"] += 1
        topic = _topic_hint(ex)
        if topic:
            topic_counter[topic] += 1
        # Lightweight language heuristic from content prefix + Unicode range.
        lang = "ru" if any("а" <= ch.lower() <= "я" for ch in txt[:400]) else "en"
        lang_counter[lang] += 1
    if topic_counter:
        top_topic, top_n = topic_counter.most_common(1)[0]
        if top_n >= int(os.getenv("POST_QUALITY_TOPIC_BURST_THRESHOLD", "4")):
            counts["repeated_topic_bursts"] = 1
    if len(lang_counter) > 1:
        major = max(lang_counter.values())
        minor = sum(lang_counter.values()) - major
        if minor >= int(os.getenv("POST_QUALITY_LANG_MIX_WARN_COUNT", "3")):
            counts["language_inconsistency"] = 1
    try:
        rej = conn.execute(
            "SELECT COUNT(*) FROM operator_feedback WHERE action='reject' AND created_at >= datetime('now', '-24 hours')"
        ).fetchone()
        if int((rej or [0])[0] or 0) >= int(os.getenv("POST_QUALITY_REJECT_SPIKE_THRESHOLD", "4")):
            counts["operator_rejection_spikes"] = 1
    except sqlite3.OperationalError:
        pass
    score = _quality_score_from_counts(counts)
    warnings = [k for k, v in counts.items() if v]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": "24h",
        "POST_QUALITY_SCORE": score,
        "warning_count": len(warnings),
        "warnings": warnings,
        "counts": counts,
        "publishes_24h": len(rows),
    }


def persist_post_quality_report(runtime_dir: str, report: dict[str, Any]) -> Path:
    path = _report_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


async def run_post_quality_heartbeat(settings: Any) -> dict[str, Any]:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    db_path = sqlite_path_from_url(raw)
    if not db_path or not Path(db_path).is_file():
        return {"skipped": True, "reason": "db_unavailable"}
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        report = build_post_quality_report(conn, runtime_dir=settings.runtime_state_dir)
    finally:
        conn.close()
    out = persist_post_quality_report(settings.runtime_state_dir, report)
    if report.get("warning_count"):
        log_event(
            logger,
            "post_quality_monitor.warning",
            score=report.get("POST_QUALITY_SCORE"),
            warnings=report.get("warnings"),
            path=str(out),
        )
    return report
