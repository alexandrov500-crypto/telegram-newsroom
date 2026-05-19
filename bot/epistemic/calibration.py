from __future__ import annotations

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.trust import TrustGraph


class HumanTrustCalibration:
    """Operator-facing trust and confidence calibration workflows."""

    def __init__(self, repository: EpistemicRepository, trust: TrustGraph) -> None:
        self._repo = repository
        self._trust = trust

    def explain_confidence_lineage(self, subject_type: str, subject_id: str) -> str:
        score = self._repo.get_score(subject_type, subject_id)
        if not score:
            return f"No epistemic score for {subject_type}:{subject_id}"
        lines = [
            f"Confidence lineage for {subject_type}:{subject_id}",
            f"  confidence: {score['confidence']:.3f}",
            f"  uncertainty: {score['uncertainty']:.3f}",
            f"  evidence_depth: {score['evidence_depth']:.3f}",
            f"  contradiction_exposure: {score['contradiction_exposure']:.3f}",
            f"  source_diversity: {score['source_diversity']:.3f}",
            f"  replay_stability: {score['replay_stability']:.3f}",
            f"  explanation: {score.get('explanation', '')[:200]}",
        ]
        with self._repo._connect() as conn:
            logs = conn.execute(
                """
                SELECT prior_confidence, posterior_confidence, delta_reason, created_at
                FROM epistemic_confidence_log WHERE score_id = ?
                ORDER BY created_at DESC LIMIT 8
                """,
                (score["score_id"],),
            ).fetchall()
        for log in logs:
            lines.append(
                f"  - {log['created_at'][-19:]}: {log['prior_confidence']:.2f} → "
                f"{log['posterior_confidence']:.2f} ({log['delta_reason'][:50]})"
            )
        return "\n".join(lines)

    def explore_contradictions(self, limit: int = 10) -> str:
        rows = self._repo.open_contradictions(limit=limit)
        if not rows:
            return "No open contradictions."
        lines = ["Open contradictions:"]
        for r in rows:
            lines.append(
                f"- [{r['contradiction_id']}] {r['subject_type']} severity={r['severity']:.2f}: "
                f"{r['explanation'][:80]}"
            )
        return "\n".join(lines)

    def override_trust(
        self,
        from_node: str,
        to_node: str,
        trust: float,
        *,
        operator_id: str | None,
        reason: str,
    ) -> None:
        self._trust.operator_override(from_node, to_node, trust, operator_id=operator_id, reason=reason)
        self._repo.record_calibration(
            "trust_override",
            "trust_edge",
            f"{from_node}->{to_node}",
            operator_id=operator_id,
            annotation=reason,
            prior=None,
            new_value=trust,
        )

    def validate_alert(self, alert_id: str, *, operator_id: str | None, accepted: bool) -> None:
        self._repo.validate_alert(alert_id, operator_id=operator_id, accepted=accepted)
        self._repo.record_calibration(
            "alert_validation",
            "alert",
            alert_id,
            operator_id=operator_id,
            annotation="accepted" if accepted else "rejected",
        )

    def challenge_consensus(
        self,
        session_id: str,
        *,
        operator_id: str | None,
        annotation: str,
    ) -> None:
        self._repo.record_calibration(
            "consensus_challenge",
            "consensus",
            session_id,
            operator_id=operator_id,
            annotation=annotation,
        )
