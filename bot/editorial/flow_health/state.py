from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

_UNSET: Any = object()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path():
    from bot.storage.db import default_db_path, init_database

    return init_database(default_db_path())


def load_state() -> dict[str, Any]:
    try:
        with sqlite3.connect(_path(), timeout=5) as conn:
            row = conn.execute(
                "SELECT recovery_activated_at, metrics_json FROM ops_flow_health_state WHERE id = 1",
            ).fetchone()
        if not row:
            return {}
        try:
            metrics = json.loads(row[1] or "{}")
        except json.JSONDecodeError:
            metrics = {}
        metrics["recovery_activated_at"] = row[0]
        return metrics
    except Exception:
        return {}


def save_state(
    *,
    recovery_activated_at: str | None | Any = _UNSET,
    metrics: dict[str, Any] | None = None,
) -> None:
    try:
        cur = load_state()
        if recovery_activated_at is not _UNSET:
            cur["recovery_activated_at"] = recovery_activated_at
        if metrics:
            cur.update(metrics)
        at = cur.get("recovery_activated_at")
        metrics_only = {k: v for k, v in cur.items() if k != "recovery_activated_at"}
        with sqlite3.connect(_path(), timeout=5) as conn:
            conn.execute(
                """
                INSERT INTO ops_flow_health_state (id, recovery_activated_at, metrics_json, updated_at)
                VALUES (1, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    recovery_activated_at = excluded.recovery_activated_at,
                    metrics_json = excluded.metrics_json,
                    updated_at = excluded.updated_at
                """,
                (at, json.dumps(metrics_only), _utcnow()),
            )
            conn.commit()
    except Exception:
        pass


def touch_recovery_activation() -> None:
    st = load_state()
    if not st.get("recovery_activated_at"):
        count = int(st.get("recovery_activation_count") or 0) + 1
        save_state(
            recovery_activated_at=_utcnow(),
            metrics={"recovery_activation_count": count},
        )


def clear_recovery_activation() -> None:
    save_state(recovery_activated_at=None)
