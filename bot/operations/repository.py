from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class OperationsRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def start_burnin(self, profile: str) -> str:
        run_id = str(uuid.uuid4())[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_burnin_runs (run_id, profile, status, started_at)
                VALUES (?, ?, 'running', ?)
                """,
                (run_id, profile, self._now()),
            )
            conn.commit()
        return run_id

    def record_burnin_sample(self, run_id: str, metrics: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_burnin_samples (run_id, sample_at, metrics_json)
                VALUES (?, ?, ?)
                """,
                (run_id, self._now(), json.dumps(metrics)),
            )
            conn.commit()

    def complete_burnin(self, run_id: str, *, health_score: float, summary: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ops_burnin_runs
                SET status = 'completed', completed_at = ?, health_score = ?, summary_json = ?
                WHERE run_id = ?
                """,
                (self._now(), health_score, json.dumps(summary), run_id),
            )
            conn.commit()

    def active_burnin(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_burnin_runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def burnin_samples(self, run_id: str, limit: int = 500) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ops_burnin_samples WHERE run_id = ? ORDER BY sample_at DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_feed_health(
        self,
        feed_url: str,
        *,
        source_name: str | None,
        reliability: float,
        malformed_delta: int = 0,
        duplicate_burst: int = 0,
        error: str | None = None,
        success: bool = True,
    ) -> None:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT malformed_count, duplicate_burst FROM ops_feed_health WHERE feed_url = ?",
                (feed_url,),
            ).fetchone()
            mal = int(row["malformed_count"]) + malformed_delta if row else malformed_delta
            dup = max(int(row["duplicate_burst"]) if row else 0, duplicate_burst)
            conn.execute(
                """
                INSERT INTO ops_feed_health
                (feed_url, source_name, reliability_score, malformed_count, duplicate_burst,
                 last_success_at, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feed_url) DO UPDATE SET
                    source_name = excluded.source_name,
                    reliability_score = excluded.reliability_score,
                    malformed_count = excluded.malformed_count,
                    duplicate_burst = excluded.duplicate_burst,
                    last_success_at = excluded.last_success_at,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    feed_url,
                    source_name,
                    reliability,
                    mal,
                    dup,
                    now if success else None,
                    error,
                    now,
                ),
            )
            conn.commit()

    def feed_health_report(self, limit: int = 30) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ops_feed_health ORDER BY reliability_score ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def save_certification(self, run_id: str, *, passed: bool, gates: list[dict]) -> None:
        passed_n = sum(1 for g in gates if g.get("passed"))
        failed_n = len(gates) - passed_n
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_certification_runs (run_id, status, gates_passed, gates_failed, report_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "passed" if passed else "failed",
                    passed_n,
                    failed_n,
                    json.dumps({"gates": gates}),
                    self._now(),
                ),
            )
            conn.commit()

    def latest_certification(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_certification_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def save_incident_bundle(self, incident_key: str, bundle: dict, *, rca: str | None = None) -> str:
        bundle_id = str(uuid.uuid4())[:12]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_incident_bundles (bundle_id, incident_key, status, bundle_json, rca_summary, created_at)
                VALUES (?, ?, 'open', ?, ?, ?)
                """,
                (bundle_id, incident_key, json.dumps(bundle), rca, self._now()),
            )
            conn.commit()
        return bundle_id

    def get_incident_bundle(self, bundle_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_incident_bundles WHERE bundle_id = ?", (bundle_id,)
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["bundle"] = json.loads(out.pop("bundle_json") or "{}")
        return out

    def record_editorial_review(
        self,
        review_type: str,
        target_id: str,
        *,
        score: float | None,
        annotation: str | None,
        useful: bool | None,
        operator_id: str | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ops_editorial_reviews
                (review_type, target_id, operator_id, score, annotation, useful, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_type,
                    target_id,
                    operator_id,
                    score,
                    annotation,
                    1 if useful else 0 if useful is not None else None,
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def editorial_review_stats(self, review_type: str | None = None) -> dict:
        q = "SELECT AVG(score) AS avg_score, AVG(useful) AS avg_useful, COUNT(*) AS n FROM ops_editorial_reviews"
        params: list[object] = []
        if review_type:
            q += " WHERE review_type = ?"
            params.append(review_type)
        with self._connect() as conn:
            row = conn.execute(q, params).fetchone()
        return {
            "count": int(row["n"] or 0),
            "avg_score": float(row["avg_score"] or 0),
            "avg_useful": float(row["avg_useful"] or 0),
        }

    def record_cost_snapshot(
        self,
        *,
        region: str | None,
        token_spend: float,
        replay_cost: float,
        cognition_cost: float,
        federation_cost: float,
        anomaly: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_cost_snapshots
                (region, token_spend, replay_cost, cognition_cost, federation_cost, anomaly_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (region, token_spend, replay_cost, cognition_cost, federation_cost, anomaly, self._now()),
            )
            conn.commit()

    def record_storage_snapshot(self, table_name: str, row_count: int, estimated_bytes: int = 0) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_storage_snapshots (table_name, row_count, estimated_bytes, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (table_name, row_count, estimated_bytes, self._now()),
            )
            conn.commit()

    def enqueue_alert(
        self,
        *,
        alert_key: str,
        category: str,
        title: str,
        priority: int,
        detail: dict | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO ops_alert_queue (alert_key, priority, category, title, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (alert_key, priority, category, title, json.dumps(detail or {}), self._now()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def triage_queue(self, *, status: str = "open", limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM ops_alert_queue
                WHERE status = ? ORDER BY priority DESC, created_at ASC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["detail"] = json.loads(item.pop("detail_json") or "{}")
            except json.JSONDecodeError:
                item["detail"] = {}
            out.append(item)
        return out

    def resolve_alert(self, alert_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE ops_alert_queue SET status = 'resolved' WHERE id = ?", (alert_id,)
            )
            conn.commit()

    def log_compaction(self, table: str, before: int, after: int, policy: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_compaction_log (target_table, rows_before, rows_after, policy, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (table, before, after, policy, self._now()),
            )
            conn.commit()

    def table_row_counts(self) -> dict[str, int]:
        tables = (
            "sourced_event_log",
            "mesh_cognitive_events",
            "epistemic_scores",
            "evaluation_results",
            "intelligence_graph_edges",
            "ops_burnin_samples",
        )
        counts: dict[str, int] = {}
        with self._connect() as conn:
            for t in tables:
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
                    counts[t] = int(row["c"])
                except sqlite3.OperationalError:
                    counts[t] = 0
        return counts

    def save_burnin_report(
        self,
        *,
        run_id: str,
        period: str,
        markdown: str,
        regressions: list[str],
        health_score: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_burnin_reports
                (run_id, period, report_markdown, regressions_json, health_score, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, period, markdown, json.dumps(regressions), health_score, self._now()),
            )
            conn.commit()

    def latest_burnin_report(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM ops_burnin_reports WHERE run_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def start_operator_session(self, session_id: str, session_type: str, operator_id: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_operator_sessions
                (session_id, operator_id, session_type, actions_count, fatigue_score, started_at)
                VALUES (?, ?, ?, 0, 0, ?)
                """,
                (session_id, operator_id, session_type, self._now()),
            )
            conn.commit()

    def record_operator_action(self, session_id: str, *, fatigue_delta: float = 0.01) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE ops_operator_sessions
                SET actions_count = actions_count + 1,
                    fatigue_score = MIN(1.0, fatigue_score + ?)
                WHERE session_id = ?
                """,
                (fatigue_delta, session_id),
            )
            conn.commit()

    def end_operator_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE ops_operator_sessions SET ended_at = ? WHERE session_id = ?",
                (self._now(), session_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM ops_operator_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def record_epistemic_longitudinal(
        self,
        *,
        confidence_mean: float,
        uncertainty_mean: float,
        open_contradictions: int,
        misinfo_pressure: float,
        diversity_score: float,
        alerts: list[str] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_epistemic_longitudinal
                (snapshot_at, confidence_mean, uncertainty_mean, open_contradictions,
                 misinfo_pressure, diversity_score, alerts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._now(),
                    confidence_mean,
                    uncertainty_mean,
                    open_contradictions,
                    misinfo_pressure,
                    diversity_score,
                    json.dumps(alerts or []),
                ),
            )
            conn.commit()

    def epistemic_longitudinal_series(self, limit: int = 200) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ops_epistemic_longitudinal ORDER BY snapshot_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def save_replay_snapshot(
        self,
        snapshot_id: str,
        *,
        subject_type: str,
        subject_id: str,
        watermark: int,
        payload: dict,
        tier: str = "hot",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_replay_snapshots
                (snapshot_id, subject_type, subject_id, sequence_watermark, snapshot_json, tier, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    subject_type,
                    subject_id,
                    watermark,
                    json.dumps(payload),
                    tier,
                    self._now(),
                ),
            )
            conn.commit()

    def get_replay_snapshot(self, subject_type: str, subject_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM ops_replay_snapshots
                WHERE subject_type = ? AND subject_id = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (subject_type, subject_id),
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["payload"] = json.loads(out.pop("snapshot_json") or "{}")
        return out

    def save_readiness_score(
        self,
        *,
        staging_score: float,
        certification_passed: bool,
        burnin_health: float,
        epistemic_stability: float,
        detail: dict,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_readiness_scores
                (staging_score, certification_passed, burnin_health, epistemic_stability, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    staging_score,
                    1 if certification_passed else 0,
                    burnin_health,
                    epistemic_stability,
                    json.dumps(detail),
                    self._now(),
                ),
            )
            conn.commit()

    def latest_readiness_score(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_readiness_scores ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def save_daily_cost_report(self, report_date: str, total: float, breakdown: dict, *, anomaly: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_daily_cost_reports (report_date, total_usd, breakdown_json, anomaly, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    total_usd = excluded.total_usd,
                    breakdown_json = excluded.breakdown_json,
                    anomaly = excluded.anomaly,
                    created_at = excluded.created_at
                """,
                (report_date, total, json.dumps(breakdown), 1 if anomaly else 0, self._now()),
            )
            conn.commit()

    def alert_exists(self, alert_key: str, *, hours: int = 24) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM ops_alert_queue
                WHERE alert_key = ? AND created_at > datetime('now', ?)
                LIMIT 1
                """,
                (alert_key, f"-{hours} hours"),
            ).fetchone()
        return row is not None

    def record_staging_publish_audit(
        self,
        *,
        correlation_id: str,
        pending_news_id: int | None,
        channel_id: int | None,
        approved: bool,
        operator_id: str | None,
        detail: dict,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_staging_publish_audit (
                    correlation_id, pending_news_id, channel_id, approved,
                    operator_id, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation_id,
                    pending_news_id,
                    channel_id,
                    1 if approved else 0,
                    operator_id,
                    json.dumps(detail),
                    self._now(),
                ),
            )
            conn.commit()

    def staging_publish_audit_count(self) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM ops_staging_publish_audit"
                ).fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0

    def operator_intervention_count(self) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM ops_operator_sessions WHERE ended_at IS NOT NULL"
                ).fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0

    def open_contradiction_count(self) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM epistemic_contradictions WHERE status = 'open'"
                ).fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0

    def pending_misinfo_alert_count(self) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM epistemic_alerts
                    WHERE status = 'pending_review'
                    """
                ).fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0

    def incident_bundle_count(self) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute("SELECT COUNT(*) AS c FROM ops_incident_bundles").fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0

    def save_incident_thread(self, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_incident_threads
                (thread_id, correlation_key, severity, title, timeline_json, replay_refs_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["thread_id"],
                    payload["correlation_key"],
                    payload["severity"],
                    payload["title"],
                    payload["timeline_json"],
                    payload.get("replay_refs_json"),
                    self._now(),
                ),
            )
            conn.commit()

    def save_console_usability_snapshot(
        self,
        *,
        delivered: int,
        suppressed: int,
        aggregated: int,
        fatigue_score: float,
        detail: dict | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_console_usability
                (delivered, suppressed, aggregated, fatigue_score, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    delivered,
                    suppressed,
                    aggregated,
                    fatigue_score,
                    json.dumps(detail or {}),
                    self._now(),
                ),
            )
            conn.commit()

    def get_feed_health(self, feed_url: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_feed_health WHERE feed_url = ?", (feed_url,)
            ).fetchone()
        return dict(row) if row else None

    def is_feed_quarantined(self, feed_url: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM ops_feed_quarantine
                WHERE feed_url = ?
                  AND (until_at IS NULL OR until_at > datetime('now'))
                LIMIT 1
                """,
                (feed_url,),
            ).fetchone()
        return row is not None

    def quarantine_feed(
        self,
        feed_url: str,
        *,
        source_name: str | None,
        reason: str,
        hours: int | None = None,
    ) -> None:
        with self._connect() as conn:
            if hours is not None:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ops_feed_quarantine
                    (feed_url, source_name, reason, quarantined_at, until_at)
                    VALUES (?, ?, ?, ?, datetime('now', ?))
                    """,
                    (feed_url, source_name, reason, self._now(), f"+{hours} hours"),
                )
            else:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ops_feed_quarantine
                    (feed_url, source_name, reason, quarantined_at, until_at)
                    VALUES (?, ?, ?, ?, NULL)
                    """,
                    (feed_url, source_name, reason, self._now()),
                )
            conn.commit()

    def increment_feed_malformed(self, feed_url: str, *, source_name: str | None) -> None:
        health = self.get_feed_health(feed_url)
        reliability = float(health["reliability_score"]) if health else 0.8
        reliability = max(0.0, reliability - 0.05)
        self.upsert_feed_health(
            feed_url,
            source_name=source_name,
            reliability=reliability,
            malformed_delta=1,
            success=False,
            error="malformed_entry",
        )

    def record_telegram_outbound(
        self,
        *,
        message_key: str,
        channel_id: int,
        success: bool,
        latency_ms: int,
        message_id: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_telegram_outbound
                (message_key, channel_id, success, latency_ms, telegram_message_id, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_key,
                    channel_id,
                    1 if success else 0,
                    latency_ms,
                    message_id,
                    error,
                    self._now(),
                ),
            )
            conn.commit()

    def telegram_delivery_failure_count(self, *, hours: int = 6) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM ops_telegram_outbound
                    WHERE success = 0
                      AND created_at > datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
                return int(row["c"]) if row else 0
            except sqlite3.OperationalError:
                return 0

    def telegram_delivery_success_rate(self, *, hours: int = 6) -> float:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS ok,
                        COUNT(*) AS total
                    FROM ops_telegram_outbound
                    WHERE created_at > datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
                total = int(row["total"] or 0)
                if total == 0:
                    return 1.0
                return float(row["ok"] or 0) / total
            except sqlite3.OperationalError:
                return 1.0

    def create_ops_incident(
        self,
        *,
        incident_id: str,
        title: str,
        severity: str,
        correlation_key: str,
        detail: str,
        replay_refs: list[str] | None = None,
        suggested_action: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_incidents
                (incident_id, status, severity, title, correlation_key, detail_json,
                 replay_refs_json, suggested_action, created_at)
                VALUES (?, 'open', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    severity,
                    title,
                    correlation_key,
                    json.dumps({"detail": detail}),
                    json.dumps(replay_refs or []),
                    suggested_action,
                    self._now(),
                ),
            )
            conn.commit()

    def update_ops_incident_status(
        self,
        incident_id: str,
        *,
        status: str,
        operator_id: str | None = None,
        note: str = "",
    ) -> bool:
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT incident_id FROM ops_incidents WHERE incident_id = ?",
                (incident_id,),
            ).fetchone()
            if row is None:
                return False
            if status == "acked":
                conn.execute(
                    """
                    UPDATE ops_incidents
                    SET status = ?, operator_id = ?, acked_at = ?
                    WHERE incident_id = ?
                    """,
                    (status, operator_id, now, incident_id),
                )
            elif status == "resolved":
                conn.execute(
                    """
                    UPDATE ops_incidents
                    SET status = ?, operator_id = ?, resolved_at = ?
                    WHERE incident_id = ?
                    """,
                    (status, operator_id, now, incident_id),
                )
            else:
                conn.execute(
                    "UPDATE ops_incidents SET status = ? WHERE incident_id = ?",
                    (status, incident_id),
                )
            conn.commit()
        return True

    def get_ops_incident(self, incident_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM ops_incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        if row is None:
            return None
        out = dict(row)
        try:
            out["replay_refs_json"] = json.loads(out.get("replay_refs_json") or "[]")
        except json.JSONDecodeError:
            out["replay_refs_json"] = []
        return out

    def list_incidents(self, *, status: str | None = None, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM ops_incidents
                    WHERE status = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ops_incidents ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def save_evidence_bundle(self, bundle_id: str, period: str, payload: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ops_evidence_bundles
                (bundle_id, period, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (bundle_id, period, json.dumps(payload), self._now()),
            )
            conn.commit()

    def burnin_samples_for_period(self, period: str, limit: int = 2000) -> list[dict]:
        hours_map = {"24h": 24, "72h": 72, "7d": 168}
        hours = hours_map.get(period, 24)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT metrics_json FROM ops_burnin_samples
                WHERE sample_at > datetime('now', ?)
                ORDER BY sample_at ASC LIMIT ?
                """,
                (f"-{hours} hours", limit),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            try:
                out.append(json.loads(row["metrics_json"]))
            except json.JSONDecodeError:
                continue
        return out

    def save_longevity_snapshot(self, period: str, metrics: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ops_longevity_snapshots (period, metrics_json, created_at)
                VALUES (?, ?, ?)
                """,
                (period, json.dumps(metrics), self._now()),
            )
            conn.commit()

    def staging_publish_mismatch_count(self, *, hours: int = 24) -> int:
        """Unapproved publishes or shadow violations in audit log."""
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM ops_staging_publish_audit
                    WHERE approved = 0
                      AND created_at > datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
                return int(row["c"]) if row else 0
            except sqlite3.OperationalError:
                return 0

    def count_stuck_approvals(self, *, hours: float = 4.0) -> int:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM pending_news
                    WHERE status = 'pending'
                      AND created_at < datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
                return int(row["c"]) if row else 0
            except sqlite3.OperationalError:
                return 0

    def operator_workflow_stats(self, *, hours: int = 24) -> dict:
        with self._connect() as conn:
            try:
                sessions = conn.execute(
                    """
                    SELECT COUNT(*) AS n,
                           AVG(fatigue_score) AS fatigue,
                           SUM(actions_count) AS actions
                    FROM ops_operator_sessions
                    WHERE started_at > datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
                reviews = conn.execute(
                    """
                    SELECT COUNT(*) AS n,
                           AVG(useful) AS useful_rate
                    FROM ops_editorial_reviews
                    WHERE created_at > datetime('now', ?)
                    """,
                    (f"-{hours} hours",),
                ).fetchone()
            except sqlite3.OperationalError:
                return {}
        return {
            "sessions": int(sessions["n"] or 0) if sessions else 0,
            "avg_fatigue": float(sessions["fatigue"] or 0) if sessions else 0.0,
            "actions": int(sessions["actions"] or 0) if sessions else 0,
            "reviews": int(reviews["n"] or 0) if reviews else 0,
            "useful_rate": float(reviews["useful_rate"] or 0) if reviews else 0.0,
        }
