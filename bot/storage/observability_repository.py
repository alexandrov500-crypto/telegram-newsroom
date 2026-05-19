from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIUsageDaily:
    usage_date: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    failure_count: int


class ObservabilityRepository:
    """Persist OpenAI usage for cost tracking and burn-in reporting."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_openai_event(
        self,
        *,
        operation: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_ms: int,
        success: bool,
        pending_news_id: int | None = None,
    ) -> None:
        total = prompt_tokens + completion_tokens
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO openai_usage_events (
                        operation, model, prompt_tokens, completion_tokens,
                        total_tokens, cost_usd, latency_ms, success,
                        pending_news_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        operation,
                        model,
                        prompt_tokens,
                        completion_tokens,
                        total,
                        cost_usd,
                        latency_ms,
                        int(success),
                        pending_news_id,
                        self._now(),
                    ),
                )
                conn.commit()
        except Exception:
            logger.exception("event=openai_usage_persist_failed operation=%s", operation)

    def aggregate_daily(self, usage_date: str | None = None) -> None:
        day = usage_date or datetime.now(timezone.utc).date().isoformat()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) AS request_count,
                        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                        COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                        COALESCE(SUM(cost_usd), 0) AS cost_usd,
                        COALESCE(SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END), 0)
                            AS failure_count
                    FROM openai_usage_events
                    WHERE date(created_at) = date(?)
                    """,
                    (day,),
                ).fetchone()
                if row is None:
                    return
                conn.execute(
                    """
                    INSERT INTO openai_usage_daily (
                        usage_date, request_count, prompt_tokens,
                        completion_tokens, cost_usd, failure_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(usage_date) DO UPDATE SET
                        request_count = excluded.request_count,
                        prompt_tokens = excluded.prompt_tokens,
                        completion_tokens = excluded.completion_tokens,
                        cost_usd = excluded.cost_usd,
                        failure_count = excluded.failure_count,
                        updated_at = excluded.updated_at
                    """,
                    (
                        day,
                        int(row["request_count"] or 0),
                        int(row["prompt_tokens"] or 0),
                        int(row["completion_tokens"] or 0),
                        float(row["cost_usd"] or 0),
                        int(row["failure_count"] or 0),
                        self._now(),
                    ),
                )
                conn.commit()
        except Exception:
            logger.exception("event=openai_daily_aggregate_failed day=%s", day)

    def get_daily(self, usage_date: str | None = None) -> OpenAIUsageDaily | None:
        day = usage_date or datetime.now(timezone.utc).date().isoformat()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT usage_date, request_count, prompt_tokens,
                           completion_tokens, cost_usd, failure_count
                    FROM openai_usage_daily
                    WHERE usage_date = ?
                    """,
                    (day,),
                ).fetchone()
            if row is None:
                return None
            return OpenAIUsageDaily(
                usage_date=str(row["usage_date"]),
                request_count=int(row["request_count"] or 0),
                prompt_tokens=int(row["prompt_tokens"] or 0),
                completion_tokens=int(row["completion_tokens"] or 0),
                cost_usd=float(row["cost_usd"] or 0),
                failure_count=int(row["failure_count"] or 0),
            )
        except Exception:
            return None

    def count_pending_queue(self) -> int:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM pending_news WHERE status = 'pending'"
                ).fetchone()
            return int(row["cnt"] or 0) if row else 0
        except Exception:
            return 0
