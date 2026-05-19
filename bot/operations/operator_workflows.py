from __future__ import annotations

import uuid
from dataclasses import dataclass

from bot.operations.ergonomics import OperationalErgonomics
from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class OperatorSessionMetrics:
    session_id: str
    actions: int
    fatigue_score: float
    session_type: str


class OperatorWorkflowValidation:
    """Real operator session tracking and workflow measurement."""

    def __init__(self, repository: OperationsRepository, ergonomics: OperationalErgonomics) -> None:
        self._repo = repository
        self._ergonomics = ergonomics

    def start_session(self, session_type: str, *, operator_id: str | None = None) -> str:
        sid = str(uuid.uuid4())[:12]
        self._repo.start_operator_session(sid, session_type, operator_id)
        return sid

    def record_triage_action(self, session_id: str, *, alert_id: int | None = None) -> None:
        self._repo.record_operator_action(session_id, fatigue_delta=0.02)
        if alert_id is not None:
            self._ergonomics.resolve(alert_id)

    def record_review(self, session_id: str, *, useful: bool) -> None:
        self._repo.record_operator_action(session_id, fatigue_delta=0.01 if useful else 0.03)

    def end_session(self, session_id: str) -> OperatorSessionMetrics | None:
        row = self._repo.end_operator_session(session_id)
        if not row:
            return None
        return OperatorSessionMetrics(
            session_id=session_id,
            actions=int(row["actions_count"]),
            fatigue_score=float(row["fatigue_score"]),
            session_type=str(row["session_type"]),
        )

    def contradiction_triage_queue(self) -> list[dict]:
        with self._repo._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT contradiction_id, severity, explanation, subject_type
                    FROM epistemic_contradictions WHERE status = 'open'
                    ORDER BY severity DESC LIMIT 15
                    """
                ).fetchall()
                return [dict(r) for r in rows]
            except Exception:
                return []

    def misinformation_review_queue(self) -> list[dict]:
        with self._repo._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT alert_id, severity, subject_id, explanation
                    FROM epistemic_alerts WHERE status = 'pending_review'
                    ORDER BY severity DESC LIMIT 15
                    """
                ).fetchall()
                return [dict(r) for r in rows]
            except Exception:
                return []
