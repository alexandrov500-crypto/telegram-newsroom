from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from bot.ops_lifecycle.archive import archive_root, ensure_archive_dirs
from bot.ops_lifecycle.db_health import database_health
from bot.ops_lifecycle.entropy import compute_entropy_metrics
from bot.ops_lifecycle.policies import default_policies
from bot.ops_lifecycle.repository import LifecycleRepository


def build_ops_storage_payload(db_path: Path) -> dict[str, Any]:
    repo = LifecycleRepository(db_path)
    health = database_health(db_path)
    runs = repo.recent_runs(limit=5)
    entropy = compute_entropy_metrics(db_path, lifecycle_runs=runs)
    state = repo.get_state()
    root = ensure_archive_dirs()

    policies = [
        {
            "name": p.name,
            "action": p.action,
            "retention_days": p.retention_days,
            "table": p.table,
        }
        for p in default_policies()
    ]

    oldest_artifacts: list[dict[str, Any]] = []
    for sub in ("backups", "pulses", "exports"):
        d = root / sub
        if d.is_dir():
            files = sorted(d.rglob("*"), key=lambda p: p.stat().st_mtime if p.is_file() else 0)
            for f in files[:3]:
                if f.is_file():
                    oldest_artifacts.append(
                        {
                            "path": str(f.relative_to(root)),
                            "size_kb": round(f.stat().st_size / 1024, 1),
                        },
                    )

    return {
        "status": "ok",
        "database": health,
        "entropy": entropy,
        "lifecycle_state": state,
        "retention_policies": policies,
        "recent_maintenance_runs": runs,
        "archive_root": str(archive_root()),
        "oldest_archives": oldest_artifacts,
    }


def build_ops_storage_html(db_path: Path) -> str:
    payload = build_ops_storage_payload(db_path)
    db = payload["database"]
    ent = payload["entropy"]
    state = payload.get("lifecycle_state") or {}

    lines = [
        "<b>Ops storage</b>",
        f"DB: <code>{html.escape(str(db.get('path', '')))}</code> · "
        f"{db.get('size_mb', 0):.1f} MB · integrity {'ok' if db.get('integrity_ok') else 'FAIL'}",
        f"Freelist pages: {db.get('freelist_count', 0)} · archive pressure: "
        f"<code>{html.escape(str(ent.get('archive_pressure', '?')))}</code>",
        "",
        "<b>Retention status</b>",
        f"Last maintenance: {state.get('last_maintenance_at') or 'never'}",
        f"Last vacuum: {state.get('last_vacuum_at') or 'never'}",
        f"Last backup: {state.get('last_backup_at') or 'never'}",
        f"Rows removed (last run): {ent.get('last_maintenance_rows_removed', 0)}",
        "",
        "<b>Top tables (rows)</b>",
    ]
    for name, count in (ent.get("top_tables") or [])[:6]:
        lines.append(f"• <code>{html.escape(str(name))}</code>: {count:,}")

    lines.append("")
    lines.append("<b>Query samples (ms)</b>")
    for key, ms in (db.get("query_samples_ms") or {}).items():
        lines.append(f"• {html.escape(key)}: {ms}")

    runs = payload.get("recent_maintenance_runs") or []
    if runs:
        lines.append("")
        lines.append("<b>Recent maintenance</b>")
        for r in runs[:3]:
            lines.append(
                f"• {r.get('created_at', '')[:16]} {r.get('run_type')} "
                f"({r.get('duration_ms')}ms)",
            )

    lines.append("")
    lines.append(f"<b>Archive root</b> <code>{html.escape(payload.get('archive_root', ''))}</code>")
    return "\n".join(lines)
