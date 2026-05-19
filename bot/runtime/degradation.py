from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.policy.types import DegradationMode

logger = logging.getLogger(__name__)

_TRANSITIONS: dict[str, frozenset[str]] = {
    DegradationMode.NORMAL.value: frozenset(
        {
            DegradationMode.PUBLISH_SAFE.value,
            DegradationMode.DEGRADED_FEDERATION.value,
            DegradationMode.LOW_MEMORY.value,
            DegradationMode.READ_ONLY.value,
            DegradationMode.REPLAY_ONLY.value,
            DegradationMode.OPERATOR_ONLY.value,
        },
    ),
    DegradationMode.PUBLISH_SAFE.value: frozenset(
        {DegradationMode.NORMAL.value, DegradationMode.READ_ONLY.value, DegradationMode.OPERATOR_ONLY.value},
    ),
    DegradationMode.DEGRADED_FEDERATION.value: frozenset(
        {DegradationMode.NORMAL.value, DegradationMode.PUBLISH_SAFE.value},
    ),
    DegradationMode.LOW_MEMORY.value: frozenset(
        {DegradationMode.NORMAL.value, DegradationMode.PUBLISH_SAFE.value},
    ),
    DegradationMode.READ_ONLY.value: frozenset(
        {DegradationMode.NORMAL.value, DegradationMode.OPERATOR_ONLY.value, DegradationMode.REPLAY_ONLY.value},
    ),
    DegradationMode.REPLAY_ONLY.value: frozenset(
        {DegradationMode.NORMAL.value, DegradationMode.OPERATOR_ONLY.value},
    ),
    DegradationMode.OPERATOR_ONLY.value: frozenset({DegradationMode.NORMAL.value}),
}


@dataclass(frozen=True)
class DegradationSnapshot:
    mode: str
    previous_mode: str | None
    reason: str
    operator_override: bool


class DegradationStateMachine:
    """Controlled cluster degradation with rollback support."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_row()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ensure_row(self) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM degradation_state WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    """
                    INSERT INTO degradation_state (id, mode, reason, updated_at)
                    VALUES (1, ?, 'initial', ?)
                    """,
                    (DegradationMode.NORMAL.value, self._now()),
                )
                conn.commit()

    def current(self) -> DegradationSnapshot:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM degradation_state WHERE id = 1").fetchone()
        return DegradationSnapshot(
            mode=str(row["mode"]),
            previous_mode=row["previous_mode"],
            reason=str(row["reason"] or ""),
            operator_override=bool(row["operator_override"]),
        )

    def transition(
        self,
        target: str,
        *,
        reason: str,
        operator: bool = False,
        force: bool = False,
    ) -> DegradationSnapshot:
        current = self.current()
        if current.mode == target:
            return current
        if not force and not operator:
            allowed = _TRANSITIONS.get(current.mode, frozenset())
            if target not in allowed:
                logger.warning(
                    "event=degradation_transition_denied from=%s to=%s",
                    current.mode,
                    target,
                )
                return current
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE degradation_state
                SET mode = ?, previous_mode = ?, reason = ?, operator_override = ?, updated_at = ?, updated_by = ?
                WHERE id = 1
                """,
                (
                    target,
                    current.mode,
                    reason[:500],
                    1 if operator else 0,
                    now,
                    "operator" if operator else "autonomous",
                ),
            )
            conn.commit()
        try:
            from bot.observability.metrics import record_degradation_transition

            record_degradation_transition(target)
        except Exception:
            pass
        logger.info(
            "event=degradation_transition from=%s to=%s reason=%s operator=%s",
            current.mode,
            target,
            reason,
            operator,
        )
        return self.current()

    def rollback(self) -> DegradationSnapshot:
        current = self.current()
        if current.previous_mode is None:
            return self.transition(DegradationMode.NORMAL.value, reason="rollback default", force=True)
        return self.transition(
            current.previous_mode,
            reason="rollback to previous",
            force=True,
        )

    def operator_set(self, mode: str, *, reason: str = "operator override") -> DegradationSnapshot:
        return self.transition(mode, reason=reason, operator=True, force=True)
