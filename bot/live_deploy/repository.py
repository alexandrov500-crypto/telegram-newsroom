from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveDeployRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def get_state(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_live_deploy_state WHERE id = 1").fetchone()
        if not row:
            return None
        d = dict(row)
        d["reports_sent"] = json.loads(d.pop("reports_sent_json", "{}"))
        return d

    def init_state(self, *, production_start_at: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ops_live_deploy_state
                (id, production_start_at, first_72h_active, reports_sent_json, updated_at)
                VALUES (1, ?, 1, '{}', ?)
                """,
                (production_start_at, _utcnow()),
            )
            conn.commit()

    def set_first_72h(self, active: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ops_live_deploy_state
                SET first_72h_active = ?, updated_at = ? WHERE id = 1
                """,
                (1 if active else 0, _utcnow()),
            )
            conn.commit()

    def mark_report_sent(self, report_key: str) -> None:
        st = self.get_state() or {"reports_sent": {}}
        sent = dict(st.get("reports_sent", {}))
        sent[report_key] = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE ops_live_deploy_state
                SET reports_sent_json = ?, updated_at = ? WHERE id = 1
                """,
                (json.dumps(sent), _utcnow()),
            )
            conn.commit()

    def report_sent(self, report_key: str) -> bool:
        st = self.get_state()
        if not st:
            return False
        return report_key in (st.get("reports_sent") or {})

    def audit_publish(
        self,
        *,
        pending_news_id: int | None,
        action: str,
        passed: bool,
        blockers: list[str],
        detail: dict[str, Any] | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_live_deploy_audit
                (pending_news_id, action, passed, blockers_json, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    pending_news_id,
                    action,
                    1 if passed else 0,
                    json.dumps(blockers),
                    json.dumps(detail or {}),
                    _utcnow(),
                ),
            )
            conn.commit()

    def save_drill(
        self,
        *,
        scenario: str,
        score: float,
        response_ms: int,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_live_deploy_drills
                (scenario, score, response_ms, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (scenario, score, response_ms, json.dumps(detail), _utcnow()),
            )
            conn.commit()
