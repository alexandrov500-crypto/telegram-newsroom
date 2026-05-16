from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from app.config import Settings
from utils.observability import get_runtime_snapshot


def build_ai_governance_report(settings: Settings) -> dict[str, Any]:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    gauges = dict(snap.get("gauges") or {})
    return {
        "report": "ai_governance",
        "schema_version": 1,
        "openai_model_configured": getattr(settings, "openai_model", ""),
        "counters": {
            "ai_cluster_calls": int(ctr.get("ai_cluster_calls", 0)),
            "ai_cluster_failures": int(ctr.get("ai_cluster_failures", 0)),
            "ai_input_tokens": int(ctr.get("ai_input_tokens", 0)),
            "ai_output_tokens": int(ctr.get("ai_output_tokens", 0)),
            "ai_cost_micro_usd": int(ctr.get("ai_cost_micro_usd", 0)),
            "openai_retries": int(ctr.get("openai_retries", 0)),
            "openai_failures": int(ctr.get("openai_failures", 0)),
        },
        "gauges": {
            "ai_last_cluster_latency_sec": gauges.get("ai_last_cluster_latency_sec"),
        },
    }


def build_runtime_summary_report(settings: Settings) -> dict[str, Any]:
    return {
        "report": "runtime_summary",
        "schema_version": 1,
        "snapshot": get_runtime_snapshot(settings),
    }


def build_moderation_report(settings: Settings) -> dict[str, Any]:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    return {
        "report": "moderation",
        "schema_version": 1,
        "counters": {
            "drafts_created": ctr.get("drafts_created", 0),
            "drafts_approved": ctr.get("drafts_approved", 0),
            "drafts_rejected": ctr.get("drafts_rejected", 0),
            "draft_edits": ctr.get("draft_edits", 0),
            "drafts_published": ctr.get("drafts_published", 0),
            "publish_failures": ctr.get("publish_failures", 0),
        },
    }


def build_publishing_report(settings: Settings) -> dict[str, Any]:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    pub = int(ctr.get("publishes", 0))
    pf = int(ctr.get("publish_failures", 0))
    return {
        "report": "publishing",
        "schema_version": 1,
        "publishes": pub,
        "publish_failures": pf,
        "scheduled_publish_fired": int(ctr.get("scheduled_publish_fired", 0)),
        "publish_success_rate": round(pub / max(1, pub + pf), 4),
    }


def build_anomaly_report(settings: Settings) -> dict[str, Any]:
    snap = get_runtime_snapshot(settings)
    ed = snap.get("editorial_intelligence") or {}
    return {
        "report": "anomalies",
        "schema_version": 1,
        "editorial_intelligence": ed,
        "tick_timing_statistics": snap.get("tick_timing_statistics") or {},
    }


def build_editorial_activity_report(settings: Settings) -> dict[str, Any]:
    import asyncio

    from db.session import close_db, init_db, session_scope
    from utils.editorial_insights import collect_editorial_insights

    async def _run() -> dict[str, Any]:
        await close_db()
        await init_db(settings.database_url)
        async with session_scope() as session:
            data = await collect_editorial_insights(session)
        await close_db()
        return data

    try:
        insights = asyncio.run(_run())
    except Exception as exc:
        insights = {"error": repr(exc)}
    return {"report": "editorial_activity", "schema_version": 1, "insights": insights}


def render_report_html(title: str, payload: dict[str, Any]) -> str:
    body = html.escape(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"/><title>"
        + html.escape(title)
        + "</title></head><body><h1>"
        + html.escape(title)
        + "</h1><pre>"
        + body
        + "</pre></body></html>"
    )


def write_report(path: Path, payload: dict[str, Any], *, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return
    if fmt == "html":
        title = str(payload.get("report") or "report")
        path.write_text(render_report_html(title, payload), encoding="utf-8")
        return
    raise ValueError("fmt must be json or html")
