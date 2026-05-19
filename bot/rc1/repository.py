from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Rc1Repository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=10)

    def save_config_fingerprint(
        self,
        *,
        fingerprint: str,
        config: dict[str, Any],
        issues: list[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_rc1_config_fingerprint
                (id, fingerprint, config_json, issues_json, updated_at)
                VALUES (1, ?, ?, ?, ?)
                """,
                (fingerprint, json.dumps(config, sort_keys=True), json.dumps(issues), _utcnow()),
            )
            conn.commit()

    def get_config_fingerprint(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_rc1_config_fingerprint WHERE id = 1").fetchone()
        if not row:
            return None
        out = dict(row)
        out["config"] = json.loads(out.pop("config_json", "{}"))
        out["issues"] = json.loads(out.pop("issues_json", "[]"))
        return out

    def get_activation(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM ops_rc1_activation WHERE id = 1").fetchone()
        return dict(row) if row else None

    def set_activation(
        self,
        *,
        stage: str,
        previous: str | None,
        operator_signoff: str | None,
        snapshot: dict[str, Any],
        rollback_point: str,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_rc1_activation
                (id, stage, previous_stage, operator_signoff, snapshot_json, rollback_point, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stage,
                    previous,
                    operator_signoff,
                    json.dumps(snapshot),
                    rollback_point,
                    _utcnow(),
                ),
            )
            conn.commit()

    def update_baseline(self, metric_name: str, value: float) -> None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mean_value, std_value, sample_count FROM ops_rc1_baselines WHERE metric_name = ?",
                (metric_name,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO ops_rc1_baselines
                    (metric_name, mean_value, std_value, sample_count, updated_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (metric_name, value, 0.0, _utcnow()),
                )
            else:
                mean, std, n = float(row[0]), float(row[1]), int(row[2])
                n1 = n + 1
                delta = value - mean
                mean_new = mean + delta / n1
                std_new = ((std**2 * n + delta * (value - mean_new)) / n1) ** 0.5 if n1 > 1 else 0.0
                conn.execute(
                    """
                    UPDATE ops_rc1_baselines
                    SET mean_value = ?, std_value = ?, sample_count = ?, updated_at = ?
                    WHERE metric_name = ?
                    """,
                    (mean_new, std_new, n1, _utcnow(), metric_name),
                )
            conn.commit()

    def get_baseline(self, metric_name: str) -> tuple[float, float] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT mean_value, std_value FROM ops_rc1_baselines WHERE metric_name = ?",
                (metric_name,),
            ).fetchone()
        return (float(row[0]), float(row[1])) if row else None

    def save_runtime_profile(self, profile: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO ops_rc1_runtime_profiles (profile_json, created_at) VALUES (?, ?)",
                (json.dumps(profile), _utcnow()),
            )
            conn.commit()

    def latest_runtime_profile(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT profile_json FROM ops_rc1_runtime_profiles ORDER BY id DESC LIMIT 1",
            ).fetchone()
        return json.loads(row["profile_json"]) if row else None

    def save_validation_scores(
        self,
        *,
        go_live_confidence: float,
        publish_integrity: float,
        detail: dict[str, Any],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO ops_rc1_validation_scores
                (go_live_confidence, publish_integrity, detail_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (go_live_confidence, publish_integrity, json.dumps(detail), _utcnow()),
            )
            conn.commit()

    def latest_validation_scores(self) -> dict[str, Any] | None:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ops_rc1_validation_scores ORDER BY id DESC LIMIT 1",
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["detail"] = json.loads(out.pop("detail_json", "{}"))
        return out
