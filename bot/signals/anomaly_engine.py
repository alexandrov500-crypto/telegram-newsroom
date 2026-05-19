from __future__ import annotations

from dataclasses import dataclass

from bot.signals.types import AnomalyType
from bot.storage.signal_repository import SignalRepository


@dataclass(frozen=True)
class AnomalyHit:
    anomaly_type: str
    scope: str
    scope_key: str
    severity: float
    baseline: float
    observed: float
    detail: dict


class AnomalyEngine:
    """Rolling-baseline anomaly detection with adaptive z-thresholds."""

    def __init__(
        self,
        repository: SignalRepository,
        *,
        z_threshold: float = 2.8,
    ) -> None:
        self._repo = repository
        self._z_threshold = z_threshold

    def observe_metric(
        self,
        *,
        scope: str,
        scope_key: str,
        metric: str,
        value: float,
        anomaly_type: str = AnomalyType.VOLUME_SPIKE.value,
    ) -> AnomalyHit | None:
        mean, std, z = self._repo.update_baseline(
            scope=scope,
            scope_key=scope_key,
            metric=metric,
            observed=value,
        )
        if abs(z) < self._z_threshold:
            return None
        severity = min(1.0, abs(z) / 5.0)
        return AnomalyHit(
            anomaly_type=anomaly_type,
            scope=scope,
            scope_key=scope_key,
            severity=severity,
            baseline=mean,
            observed=value,
            detail={"z_score": z, "std": std, "metric": metric},
        )

    def detect_source_sync(
        self,
        *,
        narrative_key: str,
        sources_in_window: list[str],
        min_sources: int = 4,
    ) -> AnomalyHit | None:
        count = len(set(sources_in_window))
        hit = self.observe_metric(
            scope="narrative",
            scope_key=narrative_key,
            metric="distinct_sources",
            value=float(count),
            anomaly_type=AnomalyType.SOURCE_SYNC.value,
        )
        if hit is None or count < min_sources:
            return None
        return hit

    def detect_sentiment_collapse(
        self,
        *,
        scope_key: str,
        previous_sentiment: float,
        current_sentiment: float,
    ) -> AnomalyHit | None:
        drop = previous_sentiment - current_sentiment
        if drop < 0.35:
            return None
        return AnomalyHit(
            anomaly_type=AnomalyType.SENTIMENT_COLLAPSE.value,
            scope="story",
            scope_key=scope_key,
            severity=min(1.0, drop),
            baseline=previous_sentiment,
            observed=current_sentiment,
            detail={"drop": drop},
        )
