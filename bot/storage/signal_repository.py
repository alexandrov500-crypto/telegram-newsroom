from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.signals.types import ImpactProfile, Signal, TrendForecast

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalRecord:
    id: int
    signal_type: str
    confidence: float
    velocity_score: float
    entities: tuple[str, ...]
    story_id: int | None
    title: str
    editorial_action: str | None
    priority_score: float | None
    created_at: str


@dataclass(frozen=True)
class AnomalyRecord:
    id: int
    anomaly_type: str
    scope: str
    scope_key: str
    severity: float
    baseline_value: float | None
    observed_value: float | None
    created_at: str


class SignalRepository:
    """Persistence for signals, anomalies, baselines, forecasts, sentiment."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_signal(
        self,
        signal: Signal,
        *,
        impact: ImpactProfile | None = None,
        forecast: TrendForecast | None = None,
        priority_score: float | None = None,
        editorial_action: str | None = None,
    ) -> int:
        now = self._now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signals (
                    signal_type, confidence, velocity_score, entities_json,
                    story_id, cluster_id, pending_news_id, source, title, summary,
                    impact_json, forecast_json, priority_score, editorial_action, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.type,
                    signal.confidence,
                    signal.velocity_score,
                    json.dumps(list(signal.entities)),
                    signal.story_id,
                    signal.cluster_id,
                    signal.pending_news_id,
                    signal.source,
                    signal.title[:500],
                    signal.summary,
                    json.dumps(asdict(impact)) if impact else None,
                    json.dumps(
                        {
                            "forecast_probability": forecast.forecast_probability,
                            "expected_impact": forecast.expected_impact,
                            "expected_reach": forecast.expected_reach,
                        }
                    )
                    if forecast
                    else None,
                    priority_score,
                    editorial_action,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_recent_signals(
        self,
        *,
        limit: int = 20,
        signal_type: str | None = None,
        since_hours: int = 24,
    ) -> list[SignalRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        query = """
            SELECT id, signal_type, confidence, velocity_score, entities_json,
                   story_id, title, editorial_action, priority_score, created_at
            FROM signals
            WHERE created_at >= ?
        """
        params: list[object] = [cutoff]
        if signal_type:
            query += " AND signal_type = ?"
            params.append(signal_type)
        query += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        records: list[SignalRecord] = []
        for row in rows:
            entities: tuple[str, ...] = ()
            raw = row["entities_json"]
            if raw:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        entities = tuple(str(e) for e in parsed)
                except json.JSONDecodeError:
                    pass
            records.append(
                SignalRecord(
                    id=int(row["id"]),
                    signal_type=str(row["signal_type"]),
                    confidence=float(row["confidence"]),
                    velocity_score=float(row["velocity_score"] or 0),
                    entities=entities,
                    story_id=row["story_id"],
                    title=str(row["title"] or ""),
                    editorial_action=row["editorial_action"],
                    priority_score=row["priority_score"],
                    created_at=str(row["created_at"]),
                ),
            )
        return records

    def save_anomaly(
        self,
        *,
        anomaly_type: str,
        scope: str,
        scope_key: str,
        severity: float,
        baseline_value: float | None,
        observed_value: float | None,
        detail: dict | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signal_anomalies (
                    anomaly_type, scope, scope_key, severity,
                    baseline_value, observed_value, detail_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    anomaly_type,
                    scope,
                    scope_key,
                    severity,
                    baseline_value,
                    observed_value,
                    json.dumps(detail or {}),
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_recent_anomalies(self, *, limit: int = 15, since_hours: int = 48) -> list[AnomalyRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, anomaly_type, scope, scope_key, severity,
                       baseline_value, observed_value, created_at
                FROM signal_anomalies
                WHERE created_at >= ?
                ORDER BY severity DESC, created_at DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ).fetchall()
        return [
            AnomalyRecord(
                id=int(row["id"]),
                anomaly_type=str(row["anomaly_type"]),
                scope=str(row["scope"]),
                scope_key=str(row["scope_key"]),
                severity=float(row["severity"]),
                baseline_value=row["baseline_value"],
                observed_value=row["observed_value"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def update_baseline(
        self,
        *,
        scope: str,
        scope_key: str,
        metric: str,
        observed: float,
        alpha: float = 0.15,
    ) -> tuple[float, float, float]:
        """Welford-style EMA baseline; returns (mean, std, z_score)."""
        now = self._now()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT mean_value, std_value, sample_count
                FROM signal_baselines
                WHERE scope = ? AND scope_key = ? AND metric = ?
                """,
                (scope, scope_key, metric),
            ).fetchone()

            if row is None:
                mean = observed
                std = max(0.01, abs(observed) * 0.25)
                count = 1
                conn.execute(
                    """
                    INSERT INTO signal_baselines (
                        scope, scope_key, metric, mean_value, std_value,
                        sample_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (scope, scope_key, metric, mean, std, count, now),
                )
            else:
                mean = float(row["mean_value"])
                std = max(0.01, float(row["std_value"]))
                count = int(row["sample_count"]) + 1
                new_mean = mean * (1 - alpha) + observed * alpha
                diff = observed - new_mean
                new_std = std * (1 - alpha) + abs(diff) * alpha
                mean, std = new_mean, max(0.01, new_std)
                conn.execute(
                    """
                    UPDATE signal_baselines
                    SET mean_value = ?, std_value = ?, sample_count = ?, updated_at = ?
                    WHERE scope = ? AND scope_key = ? AND metric = ?
                    """,
                    (mean, std, count, now, scope, scope_key, metric),
                )
            conn.commit()

        z_score = (observed - mean) / std if std > 0 else 0.0
        return mean, std, z_score

    def save_forecast(self, forecast: TrendForecast, *, signal_id: int | None = None) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signal_forecasts (
                    story_id, signal_id, forecast_probability, expected_impact,
                    expected_reach, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast.story_id,
                    signal_id,
                    forecast.forecast_probability,
                    forecast.expected_impact,
                    forecast.expected_reach,
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_forecasts(self, *, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, story_id, forecast_probability, expected_impact,
                       expected_reach, created_at
                FROM signal_forecasts
                ORDER BY forecast_probability DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_correlation(
        self,
        *,
        narrative_key: str,
        source_a: str,
        source_b: str,
        strength: float,
        origin_source: str | None = None,
        lag_seconds: float | None = None,
        propagation: dict | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO signal_correlations (
                    narrative_key, origin_source, source_a, source_b,
                    lag_seconds, strength, propagation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    narrative_key,
                    origin_source,
                    source_a,
                    source_b,
                    lag_seconds,
                    strength,
                    json.dumps(propagation or {}),
                    self._now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def save_sentiment_window(
        self,
        *,
        scope: str,
        scope_key: str,
        sentiment_score: float,
        velocity: float,
        window_hours: int = 1,
    ) -> None:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=window_hours)).isoformat()
        end = now.isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sentiment_windows (
                    scope, scope_key, sentiment_score, velocity, window_start, window_end
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (scope, scope_key, sentiment_score, velocity, start, end),
            )
            conn.execute(
                """
                DELETE FROM sentiment_windows
                WHERE window_end < ?
                """,
                ((now - timedelta(days=7)).isoformat(),),
            )
            conn.commit()

    def recent_sentiment_velocity(
        self,
        scope_key: str,
        *,
        scope: str = "story",
        limit: int = 5,
    ) -> float:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT velocity FROM sentiment_windows
                WHERE scope = ? AND scope_key = ?
                ORDER BY window_end DESC
                LIMIT ?
                """,
                (scope, scope_key, limit),
            ).fetchall()
        if not rows:
            return 0.0
        return sum(float(row["velocity"]) for row in rows) / len(rows)

    def upsert_credibility(
        self,
        *,
        source_name: str,
        credibility_score: float,
        risk_score: float,
        bias_profile: dict[str, float],
        sensationalism: float,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_credibility_snapshots (
                    source_name, credibility_score, risk_score, bias_profile_json,
                    sensationalism, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    credibility_score = excluded.credibility_score,
                    risk_score = excluded.risk_score,
                    bias_profile_json = excluded.bias_profile_json,
                    sensationalism = excluded.sensationalism,
                    updated_at = excluded.updated_at
                """,
                (
                    source_name,
                    credibility_score,
                    risk_score,
                    json.dumps(bias_profile),
                    sensationalism,
                    self._now(),
                ),
            )
            conn.commit()

    def list_credibility(self, *, limit: int = 15) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source_name, credibility_score, risk_score,
                       bias_profile_json, sensationalism, updated_at
                FROM source_credibility_snapshots
                ORDER BY risk_score DESC, credibility_score ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            bias = {}
            try:
                bias = json.loads(row["bias_profile_json"] or "{}")
            except json.JSONDecodeError:
                pass
            out.append(
                {
                    "source_name": row["source_name"],
                    "credibility_score": float(row["credibility_score"]),
                    "risk_score": float(row["risk_score"]),
                    "bias_profile": bias,
                    "sensationalism": float(row["sensationalism"] or 0),
                },
            )
        return out

    def count_signals_since(self, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM signals WHERE created_at >= ?",
                (since_iso,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def prune_old_signals(self, *, days: int = 30) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM signals WHERE created_at < ?", (cutoff,))
            conn.commit()
            return int(cur.rowcount)
