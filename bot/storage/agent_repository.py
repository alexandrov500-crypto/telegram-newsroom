from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.editorial.agents import RiskAssessment

logger = logging.getLogger(__name__)

ACTION_RISK_ASSESSED = "risk_assessed"
ACTION_AUTO_APPROVED = "auto_approved"
ACTION_BREAKING_ALERT = "breaking_alert"
ACTION_HUMAN_REVIEW = "human_review_required"
ACTION_REVERSED = "reversed"


@dataclass(frozen=True)
class AgentActionRecord:
    id: int
    pending_news_id: int
    action_type: str
    decision_json: str | None
    reversible: bool
    reversed_at: str | None
    created_at: str


@dataclass(frozen=True)
class RiskAssessmentRecord:
    id: int
    pending_news_id: int
    risk_score: float
    confidence_score: float
    factors_json: str | None
    blocked_categories_json: str | None
    requires_human_review: bool
    created_at: str


class AgentRepository:
    """Audit trail for editorial agent decisions."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_risk_assessment(
        self,
        pending_news_id: int,
        assessment: RiskAssessment,
    ) -> int | None:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO editorial_risk_assessments (
                        pending_news_id, risk_score, confidence_score,
                        factors_json, blocked_categories_json,
                        requires_human_review, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pending_news_id,
                        assessment.risk_score,
                        assessment.publish_confidence,
                        json.dumps(list(assessment.risk_factors)),
                        json.dumps(list(assessment.blocked_categories)),
                        int(assessment.requires_human_review),
                        self._now(),
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except Exception:
            logger.exception(
                "event=agent_action_failed action=save_risk pending_news_id=%d",
                pending_news_id,
            )
            return None

    def get_latest_risk_assessment(self, pending_news_id: int) -> RiskAssessmentRecord | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id, pending_news_id, risk_score, confidence_score,
                           factors_json, blocked_categories_json,
                           requires_human_review, created_at
                    FROM editorial_risk_assessments
                    WHERE pending_news_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (pending_news_id,),
                ).fetchone()
            if row is None:
                return None
            return RiskAssessmentRecord(
                id=int(row["id"]),
                pending_news_id=int(row["pending_news_id"]),
                risk_score=float(row["risk_score"]),
                confidence_score=float(row["confidence_score"]),
                factors_json=row["factors_json"],
                blocked_categories_json=row["blocked_categories_json"],
                requires_human_review=bool(row["requires_human_review"]),
                created_at=str(row["created_at"]),
            )
        except Exception:
            logger.exception(
                "event=agent_action_failed action=get_risk pending_news_id=%d",
                pending_news_id,
            )
            return None

    def record_action(
        self,
        *,
        pending_news_id: int,
        action_type: str,
        decision: dict | None = None,
        reversible: bool = False,
    ) -> int | None:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO editorial_agent_actions (
                        pending_news_id, action_type, decision_json,
                        reversible, reversed_at, created_at
                    ) VALUES (?, ?, ?, ?, NULL, ?)
                    """,
                    (
                        pending_news_id,
                        action_type,
                        json.dumps(decision or {}),
                        int(reversible),
                        self._now(),
                    ),
                )
                conn.commit()
                return int(cur.lastrowid)
        except Exception:
            logger.exception(
                "event=agent_action_failed action=record type=%s pending_news_id=%d",
                action_type,
                pending_news_id,
            )
            return None

    def reverse_action(self, action_id: int) -> bool:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE editorial_agent_actions
                    SET reversed_at = ?
                    WHERE id = ? AND reversed_at IS NULL AND reversible = 1
                    """,
                    (self._now(), action_id),
                )
                conn.commit()
                if cur.rowcount > 0:
                    logger.info("event=agent_decision_reversed action_id=%d", action_id)
                return cur.rowcount > 0
        except Exception:
            logger.exception("event=agent_action_failed action=reverse action_id=%d", action_id)
            return False

    def reverse_latest_auto_approval(self, pending_news_id: int) -> bool:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT id FROM editorial_agent_actions
                    WHERE pending_news_id = ?
                      AND action_type = ?
                      AND reversed_at IS NULL
                      AND reversible = 1
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (pending_news_id, ACTION_AUTO_APPROVED),
                ).fetchone()
            if row is None:
                return False
            return self.reverse_action(int(row["id"]))
        except Exception:
            return False

    def recent_actions(self, *, limit: int = 15) -> list[AgentActionRecord]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, pending_news_id, action_type, decision_json,
                           reversible, reversed_at, created_at
                    FROM editorial_agent_actions
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [
                AgentActionRecord(
                    id=int(row["id"]),
                    pending_news_id=int(row["pending_news_id"]),
                    action_type=str(row["action_type"]),
                    decision_json=row["decision_json"],
                    reversible=bool(row["reversible"]),
                    reversed_at=row["reversed_at"],
                    created_at=str(row["created_at"]),
                )
                for row in rows
            ]
        except Exception:
            logger.exception("event=agent_action_failed action=recent")
            return []

    def adaptive_penalty_from_reversals(self, source: str | None) -> float:
        """Bounded learning signal from reversed auto-approvals for a source."""
        if not source:
            return 0.0
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM editorial_agent_actions a
                    JOIN pending_news p ON p.id = a.pending_news_id
                    WHERE a.action_type = ?
                      AND a.reversed_at IS NOT NULL
                      AND p.source = ?
                    """,
                    (ACTION_AUTO_APPROVED, source),
                ).fetchone()
            count = int(row["cnt"] or 0) if row else 0
            return min(0.12, count * 0.04)
        except Exception:
            return 0.0
