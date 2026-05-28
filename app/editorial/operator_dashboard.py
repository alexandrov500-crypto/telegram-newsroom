"""Human-readable operator dashboard for /ops newsroom (no raw logs)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings
from app.editorial.staging_mode import is_final_staging_mode
from app.editorial.trust_mode import is_high_trust_mode
from utils.database_url import sqlite_path_from_url


def _connect() -> sqlite3.Connection | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    if not path:
        return None
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        try:
            return sqlite3.connect(path, timeout=2.0)
        except Exception:
            return None


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    try:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0
    except sqlite3.Error:
        return 0


def build_newsroom_dashboard(settings: Settings | None = None) -> dict[str, Any]:
    """Aggregate pipeline, drafts, trust, and staging signals for operators."""
    from app.observability.staging_health import staging_health_snapshot
    from app.ops.runtime.node_role import resolve_execution_profile
    from app.reliability.auto_maintenance import auto_maintenance_snapshot

    snap = staging_health_snapshot()
    profile = None
    maintenance = {}
    runtime_dir = os.getenv("RUNTIME_STATE_DIR", "var/runtime").strip() or "var/runtime"
    if settings is not None:
        try:
            profile = resolve_execution_profile(settings).to_dict()
        except Exception:
            profile = None
        runtime_dir = settings.runtime_state_dir
    maintenance = auto_maintenance_snapshot(runtime_dir)

    pending = failed = published_24h = 0
    tier_dist = {"tier1": 0, "tier2": 0, "tier3": 0, "unknown": 0}
    conn = _connect()
    if conn:
        try:
            pending = _count(conn, "SELECT COUNT(*) FROM drafts WHERE status='pending'")
            failed = _count(conn, "SELECT COUNT(*) FROM drafts WHERE status='failed'")
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            published_24h = _count(
                conn,
                """
                SELECT COUNT(*) FROM published_posts pp
                JOIN drafts d ON d.id = pp.draft_id
                WHERE pp.published_at >= ?
                """,
                (since,),
            )
            rows = conn.execute(
                "SELECT sources FROM drafts WHERE status IN ('pending','approved') LIMIT 50"
            ).fetchall()
            from app.editorial.source_tiers import aggregate_source_tier

            for (src_json,) in rows:
                try:
                    data = json.loads(src_json or "[]")
                    chans = [str(x.get("channel") or "") for x in data if isinstance(x, dict)]
                except (json.JSONDecodeError, TypeError):
                    chans = []
                t = aggregate_source_tier(chans, runtime_dir=runtime_dir).tier
                key = f"tier{t}" if t in (1, 2, 3) else "unknown"
                tier_dist[key] = tier_dist.get(key, 0) + 1
        finally:
            conn.close()

    trust_alerts: list[str] = []
    for alert in snap.get("alerts") or []:
        if isinstance(alert, str) and any(
            k in alert.lower() for k in ("trust", "governance", "staging", "tick", "publish")
        ):
            trust_alerts.append(alert)

    pipeline = snap.get("pipeline") or {}
    publishing = snap.get("publishing") or {}
    telegram: dict[str, Any] = {}
    try:
        from app.runtime.telegram_connectivity import build_telegram_connectivity_snapshot

        telegram = build_telegram_connectivity_snapshot()
    except Exception:
        telegram = {}

    try:
        from app.ops.control_plane.guards import emergency_halt_active, publish_allowed_now
        from app.ops.control_plane.state import get_ops_state

        ops = get_ops_state()
        pub_ok, pub_reason = publish_allowed_now()
        telegram["ops_emergency_halt"] = emergency_halt_active()
        telegram["publish_allowed"] = pub_ok
        telegram["publish_block_reason"] = pub_reason if not pub_ok else ""
        telegram["publish_rate_limit_per_min"] = ops.publish_rate_limit_per_min
    except Exception:
        pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_mode": pipeline.get("mode") or pipeline.get("last_tick_status") or "unknown",
        "pending_reviews": pending,
        "failed_drafts": failed,
        "published_last_24h": published_24h,
        "publish_latency_hint_ms": publishing.get("avg_publish_ms"),
        "stuck_tasks_hint": pipeline.get("stuck_stage") or maintenance.get("reason"),
        "recent_publishes": publishing.get("recent_count_1h"),
        "trust_alerts": trust_alerts[:8],
        "source_tier_distribution": tier_dist,
        "silent_tick_alerts": [
            a for a in (snap.get("alerts") or []) if isinstance(a, str) and "tick" in a.lower()
        ][:5],
        "flags": {
            "final_staging_mode": is_final_staging_mode(settings),
            "trust_mode_high": is_high_trust_mode(settings),
            "auto_maintenance": bool(maintenance.get("active")),
        },
        "execution_profile": profile,
        "telegram": telegram,
    }


def render_newsroom_dashboard_ru(data: dict[str, Any]) -> str:
    """Plain-text Russian dashboard for CLI / bot."""
    tg = data.get("telegram") or {}
    lines = [
        "📋 Панель newsroom",
        f"Режим конвейера: {data.get('pipeline_mode', '—')}",
        f"Ожидают проверки: {data.get('pending_reviews', 0)}",
        f"Черновики с ошибкой: {data.get('failed_drafts', 0)}",
        f"Опубликовано за 24 ч: {data.get('published_last_24h', 0)}",
    ]
    if tg.get("bot_api_status"):
        lines.append(f"Telegram Bot API: {tg.get('bot_api_status')} (retry={tg.get('polling_retry_count', 0)})")
    if tg.get("conflict_detected"):
        lines.append("⚠️ Конфликт polling — остановите второй инстанс бота")
    cc = tg.get("collect_cycle") or {}
    if cc.get("collect_in_progress"):
        lines.append(
            f"Сбор данных: в процессе {cc.get('collect_elapsed_sec', '?')} с"
            + (" ⚠️ ЗАВИС" if cc.get("collect_stalled") else "")
        )
    if tg.get("last_successful_collect_at"):
        lines.append(f"Последний успешный collect: {tg['last_successful_collect_at']}")
    if tg.get("last_successful_publish_at"):
        lines.append(f"Последняя публикация: {tg['last_successful_publish_at']}")
    if tg.get("dc_reachable") is False:
        lines.append("⚠️ Telegram DC недоступен (VPN/firewall)")
    if tg.get("ops_emergency_halt"):
        lines.append("🛑 OPS emergency_halt — автопубликация остановлена")
    elif tg.get("publish_allowed") is False:
        lines.append(f"⏸ Публикация: {tg.get('publish_block_reason', 'blocked')}")
    lat = data.get("publish_latency_hint_ms")
    if lat is not None:
        lines.append(f"Задержка публикации (ср.): {lat} мс")
    stuck = data.get("stuck_tasks_hint")
    if stuck:
        lines.append(f"Застрявшие задачи: {stuck}")
    recent = data.get("recent_publishes")
    if recent is not None:
        lines.append(f"Публикаций за час: {recent}")
    flags = data.get("flags") or {}
    if flags.get("final_staging_mode"):
        lines.append("⚙️ FINAL_STAGING_MODE: включён")
    if flags.get("trust_mode_high"):
        lines.append("⚙️ NEWSROOM_TRUST_MODE=high")
    if flags.get("auto_maintenance"):
        lines.append("⚠️ Авто-обслуживание: публикация приостановлена")
    dist = data.get("source_tier_distribution") or {}
    lines.append(
        f"Источники (ожидающие): T1={dist.get('tier1', 0)} T2={dist.get('tier2', 0)} T3={dist.get('tier3', 0)}"
    )
    alerts = data.get("trust_alerts") or []
    if alerts:
        lines.append("Предупреждения доверия:")
        for a in alerts[:5]:
            lines.append(f"  • {a}")
    silent = data.get("silent_tick_alerts") or []
    if silent:
        lines.append("Тики:")
        for a in silent[:3]:
            lines.append(f"  • {a}")
    return "\n".join(lines)
