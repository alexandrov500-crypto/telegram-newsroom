from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from bot.operator_ux.attention import build_attention_queue_html
from bot.operator_ux.collector import collect_operational_context
from bot.operator_ux.dashboard import build_live_dashboard_html
from bot.operator_ux.dedupe import AlertBundler, AttentionItem
from bot.operator_ux.digest import build_operator_digest_dict, build_operator_digest_html
from bot.operator_ux.quiet import should_deliver
from bot.operator_ux.repository import AttentionMetricsRepository
from bot.operator_ux.severity import AttentionSeverity, classify_runtime_anomaly
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)

_bundler = AlertBundler(window_minutes=20)


def get_attention_repo(db_path: Path | None = None) -> AttentionMetricsRepository:
    return AttentionMetricsRepository(init_database(db_path or default_db_path()))


def gather_context(
    *,
    db_path: Path | None = None,
    base_url: str = "http://127.0.0.1:8080",
) -> dict[str, Any]:
    try:
        return collect_operational_context(db_path=db_path, base_url=base_url)
    except Exception:
        logger.debug("event=operator_ux_collect_failed")
        return {"pulse": {}, "priority_queue": [], "noise_metrics": {}}


def operator_digest_html(*, db_path: Path | None = None, base_url: str = "http://127.0.0.1:8080") -> str:
    ctx = gather_context(db_path=db_path, base_url=base_url)
    try:
        from bot.editorial.flow_health.low_observability import touch_operator_digest_seen

        touch_operator_digest_seen()
    except Exception:
        pass
    return build_operator_digest_html(ctx)


def attention_queue_html(*, db_path: Path | None = None, base_url: str = "http://127.0.0.1:8080") -> str:
    ctx = gather_context(db_path=db_path, base_url=base_url)
    return build_attention_queue_html(ctx)


def enhanced_dashboard_html(
    coordinator: Any,
    signals: dict[str, Any] | None = None,
    *,
    db_path: Path | None = None,
) -> str:
    ctx = gather_context(db_path=db_path)
    snap = coordinator.snapshot()
    return build_live_dashboard_html(
        coordinator_snap=snap,
        signals=signals,
        ctx=ctx,
    )


def record_attention_signal(
    *,
    category: str,
    title: str,
    severity: AttentionSeverity,
    detail: str = "",
    force: bool = False,
    db_path: Path | None = None,
) -> bool:
    """Dedupe + quiet hours + metrics. Returns whether would deliver."""
    item = AttentionItem(severity=severity, category=category, title=title, detail=detail)
    deliver = should_deliver(severity, force=force)
    to_send = _bundler.add(item) if deliver else None
    suppressed = deliver and to_send is None
    try:
        repo = get_attention_repo(db_path)
        repo.log_attention(
            item,
            delivered=bool(to_send) and deliver,
            suppressed=suppressed or not deliver,
        )
    except Exception:
        pass
    return bool(to_send) and deliver


def ingest_pulse_anomalies(pulse: dict[str, Any], *, db_path: Path | None = None) -> list[str]:
    """Bundle runtime anomalies into summary lines for digest/dashboard."""
    lines: list[str] = []
    for anomaly in pulse.get("anomalies") or []:
        sev = classify_runtime_anomaly(anomaly)
        title = str(anomaly.get("title") or anomaly.get("type") or "anomaly")
        record_attention_signal(
            category="runtime",
            title=title,
            severity=sev,
            detail=str(anomaly.get("detail") or "")[:120],
            db_path=db_path,
        )
    lines.extend(_bundler.bundle_summary_lines())
    return lines


def save_daily_digest_snapshot(*, db_path: Path | None = None, base_url: str = "http://127.0.0.1:8080") -> dict[str, Any]:
    from datetime import datetime, timezone

    ctx = gather_context(db_path=db_path, base_url=base_url)
    snap = build_operator_digest_dict(ctx)
    day = datetime.now(timezone.utc).date().isoformat()
    try:
        get_attention_repo(db_path).save_daily(day, snap)
    except Exception:
        pass
    return snap
