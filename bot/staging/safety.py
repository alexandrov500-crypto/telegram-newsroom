from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishSafetyVerdict:
    allowed: bool
    warnings: tuple[str, ...]
    blocked_reason: str | None = None


class StagingSafetyEnforcer:
    """Fail-safe publish gates for staging — no uncontrolled public autopublish."""

    CONFIDENCE_WARN = 0.55
    CONTRADICTION_WARN = 3
    MISINFO_BLOCK = 0.85

    def evaluate(
        self,
        *,
        auto_approval: bool,
        publish_confidence: float | None,
        open_contradictions: int = 0,
        misinfo_score: float = 0.0,
        governance_allowed: bool = True,
        operator_approved: bool = False,
        staging_mode: bool = False,
    ) -> PublishSafetyVerdict:
        warnings: list[str] = []
        if staging_mode and not operator_approved:
            return PublishSafetyVerdict(
                False,
                warnings=(),
                blocked_reason="staging_requires_operator_approval",
            )
        if not governance_allowed:
            return PublishSafetyVerdict(
                False,
                warnings=(),
                blocked_reason="governance_denied",
            )
        if misinfo_score >= self.MISINFO_BLOCK and not operator_approved:
            return PublishSafetyVerdict(
                False,
                warnings=("misinformation_risk",),
                blocked_reason="misinformation_gate",
            )
        if open_contradictions >= self.CONTRADICTION_WARN and not operator_approved:
            warnings.append("open_contradictions")
        conf = publish_confidence if publish_confidence is not None else 0.5
        if conf < self.CONFIDENCE_WARN and not operator_approved:
            warnings.append("low_confidence")
        if auto_approval and not operator_approved:
            return PublishSafetyVerdict(
                False,
                warnings=tuple(warnings) + ("auto_approval_disabled_staging",),
                blocked_reason="staging_requires_operator_approval",
            )
        if warnings and not operator_approved:
            return PublishSafetyVerdict(
                False,
                tuple(warnings),
                blocked_reason="operator_approval_required",
            )
        return PublishSafetyVerdict(True, tuple(warnings))
