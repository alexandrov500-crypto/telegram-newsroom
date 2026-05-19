from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ReplayCheckpoint:
    checkpoint_key: str
    last_sequence_id: int
    lane: str
    rate_limit_per_sec: float


class ReplayGuard:
    """Bounded, rate-limited replay with publish safety."""

    def __init__(self, db_path: Path, *, publish_idempotency: Any | None = None) -> None:
        self._db_path = db_path
        self._idempotency = publish_idempotency
        self._lane_tokens: dict[str, float] = {}
        self._last_publish_replay_ts = 0.0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_checkpoint(self, key: str = "global") -> ReplayCheckpoint:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM replay_checkpoints WHERE checkpoint_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return ReplayCheckpoint(key, 0, "default", 50.0)
        return ReplayCheckpoint(
            str(row["checkpoint_key"]),
            int(row["last_sequence_id"]),
            str(row["lane"]),
            float(row["rate_limit_per_sec"]),
        )

    def save_checkpoint(self, cp: ReplayCheckpoint) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO replay_checkpoints (
                    checkpoint_key, last_sequence_id, lane, rate_limit_per_sec, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(checkpoint_key) DO UPDATE SET
                    last_sequence_id = excluded.last_sequence_id,
                    lane = excluded.lane,
                    rate_limit_per_sec = excluded.rate_limit_per_sec,
                    updated_at = excluded.updated_at
                """,
                (cp.checkpoint_key, cp.last_sequence_id, cp.lane, cp.rate_limit_per_sec, self._now()),
            )
            conn.commit()

    def allow_replay_batch(
        self,
        *,
        lane: str = "default",
        batch_size: int = 50,
        window_sec: float = 1.0,
    ) -> int:
        """Return permitted replay count this tick (rate limit)."""
        cp = self.get_checkpoint(lane)
        now = time.monotonic()
        last = self._lane_tokens.get(lane, 0.0)
        if now - last < window_sec:
            return 0
        self._lane_tokens[lane] = now
        return min(batch_size, int(cp.rate_limit_per_sec * window_sec))

    def verify_publish_safe(self, event_type: str) -> bool:
        """Block replay from re-triggering publish workflows without idempotency."""
        if "publish" not in event_type.lower():
            return True
        if self._idempotency is None:
            logger.warning("event=replay_publish_no_idempotency")
            return False
        return True

    def plan_replay_window(
        self,
        sourced_store: Any,
        *,
        from_sequence: int | None = None,
        limit: int = 100,
        lane: str = "isolated",
    ) -> tuple[int, int]:
        """Returns (from_seq, permitted_count)."""
        cp = self.get_checkpoint(lane)
        start = from_sequence if from_sequence is not None else cp.last_sequence_id + 1
        permitted = self.allow_replay_batch(lane=lane, batch_size=limit)
        if permitted <= 0:
            return start, 0
        envelopes = sourced_store.replay_range(from_sequence=start, limit=permitted)
        safe: list = []
        for env in envelopes:
            if not self.verify_publish_safe(env.event_type):
                continue
            safe.append(env)
        end_seq = start + len(safe) - 1 if safe else cp.last_sequence_id
        if safe:
            self.save_checkpoint(
                ReplayCheckpoint(lane, end_seq, lane, cp.rate_limit_per_sec),
            )
        try:
            from bot.observability.metrics import record_stream_replay

            record_stream_replay(len(safe))
        except Exception:
            pass
        return start, len(safe)
