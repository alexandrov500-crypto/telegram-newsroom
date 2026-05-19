from __future__ import annotations

import logging

from bot.adaptive.feedback import EditorialFeedbackLoop
from bot.adaptive.policies import PolicyEngine
from bot.learning.types import FeedbackSignal
from bot.storage.learning_repository import LearningRepository

logger = logging.getLogger(__name__)

_TUNING_SPECS: dict[str, tuple[float, float, float]] = {
    "anomaly_z_threshold": (2.0, 2.8, 4.0),
    "escalation_threshold": (0.55, 0.72, 0.92),
    "suppress_below": (0.15, 0.28, 0.5),
    "digest_min_score": (0.35, 0.45, 0.7),
}


class SelfTuningEngine:
    """Bounded, auditable threshold adjustments from feedback."""

    MAX_STEP = 0.04

    def __init__(
        self,
        repository: LearningRepository,
        policies: PolicyEngine,
        feedback: EditorialFeedbackLoop,
    ) -> None:
        self._repo = repository
        self._policies = policies
        self._feedback = feedback

    def sync_from_policy(self) -> None:
        policy = self._policies.active_policy()
        for key, (_, default, _) in _TUNING_SPECS.items():
            value = float(getattr(policy, key, default))
            lo, dflt, hi = _TUNING_SPECS[key]
            self._repo.set_tuning(
                key,
                current=value,
                default=dflt,
                min_value=lo,
                max_value=hi,
            )

    def apply_feedback(self, signals: list[FeedbackSignal]) -> dict[str, float]:
        adjustments: dict[str, float] = {}
        policy = self._policies.active_policy()
        updates: dict[str, float] = {}

        for signal in signals:
            if signal.target not in _TUNING_SPECS:
                continue
            lo, default, hi = _TUNING_SPECS[signal.target]
            current = self._repo.get_tuning(signal.target, float(getattr(policy, signal.target, default)))
            delta = max(-self.MAX_STEP, min(self.MAX_STEP, signal.weight))
            if signal.kind.startswith("raise"):
                new_val = min(hi, current + abs(delta))
            else:
                new_val = max(lo, current - abs(delta))
            if abs(new_val - current) < 0.001:
                continue
            self._repo.set_tuning(
                signal.target,
                current=new_val,
                default=default,
                min_value=lo,
                max_value=hi,
                log_entry={
                    "kind": signal.kind,
                    "from": current,
                    "to": new_val,
                    "weight": signal.weight,
                },
            )
            adjustments[signal.target] = new_val
            updates[signal.target] = new_val

        if updates:
            self._policies.update_policy(**updates)
            logger.info("event=adaptive_tuning_applied updates=%s", updates)
        return adjustments

    def rollback_param(self, param_key: str) -> float:
        if param_key not in _TUNING_SPECS:
            return 0.0
        lo, default, hi = _TUNING_SPECS[param_key]
        self._repo.set_tuning(
            param_key,
            current=default,
            default=default,
            min_value=lo,
            max_value=hi,
            log_entry={"rollback": True},
        )
        self._policies.update_policy(**{param_key: default})
        return default
