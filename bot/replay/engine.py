from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from bot.adaptive.policies import PolicyEngine
from bot.storage.event_store import EventStore
from bot.storage.learning_repository import LearningRepository
from bot.storage.signal_repository import SignalRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    run_id: int
    events_processed: int
    signals_matched: int
    policy_name: str
    summary: dict


class ReplayEngine:
    """Deterministic replay of event log and signal history for regression analysis."""

    def __init__(
        self,
        db_path: Path,
        *,
        learning: LearningRepository,
        policies: PolicyEngine,
    ) -> None:
        self._db_path = db_path
        self._learning = learning
        self._policies = policies
        self._events = EventStore(db_path)
        self._signals = SignalRepository(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def run(
        self,
        *,
        from_ts: str,
        to_ts: str,
        run_label: str = "manual",
    ) -> ReplayResult:
        policy = self._policies.active_policy()
        events_processed = 0
        signals_matched = 0

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM newsroom_event_log
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at ASC
                """,
                (from_ts, to_ts),
            ).fetchall()

        for row in rows:
            events_processed += 1
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = {}
            if row["event_type"] == "SignalDetected":
                conf = float(payload.get("confidence", 0))
                if conf >= policy.escalation_threshold:
                    signals_matched += 1

        with self._connect() as conn:
            sig_rows = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM signals
                WHERE created_at >= ? AND created_at <= ?
                """,
                (from_ts, to_ts),
            ).fetchone()
        historical_signals = int(sig_rows["cnt"]) if sig_rows else 0

        summary = {
            "events_processed": events_processed,
            "signals_matched": signals_matched,
            "historical_signals": historical_signals,
            "policy_mode": policy.mode,
            "from_ts": from_ts,
            "to_ts": to_ts,
        }
        run_id = self._learning.save_replay_run(
            run_label=run_label,
            from_ts=from_ts,
            to_ts=to_ts,
            events_processed=events_processed,
            signals_matched=signals_matched,
            policy_name=policy.name,
            summary=summary,
        )
        from bot.observability.metrics import record_replay_run

        record_replay_run()
        logger.info("event=replay_completed run_id=%d summary=%s", run_id, summary)
        return ReplayResult(
            run_id=run_id,
            events_processed=events_processed,
            signals_matched=signals_matched,
            policy_name=policy.name,
            summary=summary,
        )
