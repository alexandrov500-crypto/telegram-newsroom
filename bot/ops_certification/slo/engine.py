from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SloName(str, Enum):
    PUBLISH_LATENCY = "publish_latency"
    COGNITION_LATENCY = "cognition_latency"
    DELIVERY_SUCCESS = "delivery_success"
    UPTIME = "uptime"
    OPERATOR_RESPONSE = "operator_response"
    QUEUE_DRAIN = "queue_drain"


# Target thresholds (SLO objectives)
_SLO_TARGETS: dict[SloName, dict[str, float]] = {
    SloName.PUBLISH_LATENCY: {"p99_sec": 30.0, "compliance": 0.99},
    SloName.COGNITION_LATENCY: {"p99_sec": 120.0, "compliance": 0.95},
    SloName.DELIVERY_SUCCESS: {"ratio": 0.995, "compliance": 0.995},
    SloName.UPTIME: {"ratio": 0.999, "compliance": 0.999},
    SloName.OPERATOR_RESPONSE: {"p99_sec": 300.0, "compliance": 0.90},
    SloName.QUEUE_DRAIN: {"max_depth": 400.0, "compliance": 0.95},
}


@dataclass
class SloWindowSample:
    at: float
    value: float
    success: bool


@dataclass
class SloEvaluation:
    name: SloName
    compliance_ratio: float
    burn_rate: float
    error_budget_remaining: float
    violated: bool
    window_hours: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "compliance_ratio": round(self.compliance_ratio, 4),
            "burn_rate": round(self.burn_rate, 4),
            "error_budget_remaining": round(self.error_budget_remaining, 4),
            "violated": self.violated,
            "window_hours": self.window_hours,
        }


@dataclass
class SloEngine:
    """Rolling SLO windows with burn-rate and error budget tracking."""

    window_hours: float = 1.0
    _samples: dict[SloName, deque[SloWindowSample]] = field(
        default_factory=lambda: {s: deque(maxlen=500) for s in SloName},
    )

    def record(
        self,
        slo: SloName,
        *,
        value: float,
        success: bool | None = None,
    ) -> None:
        ok = success if success is not None else value >= _SLO_TARGETS[slo].get("compliance", 0.9)
        self._samples[slo].append(SloWindowSample(at=time.time(), value=value, success=ok))
        try:
            from bot.observability.metrics import record_slo_sample

            record_slo_sample(slo.value, ok)
        except Exception:
            pass

    def _export_gauges(self, ev: SloEvaluation) -> None:
        try:
            from bot.observability.metrics import set_slo_gauges

            set_slo_gauges(ev.name.value, ev.compliance_ratio, ev.burn_rate)
        except Exception:
            pass

    def evaluate(self, slo: SloName) -> SloEvaluation:
        target = _SLO_TARGETS[slo]
        target_compliance = target.get("compliance", 0.99)
        cutoff = time.time() - self.window_hours * 3600
        samples = [s for s in self._samples[slo] if s.at >= cutoff]
        if not samples:
            return SloEvaluation(
                name=slo,
                compliance_ratio=1.0,
                burn_rate=0.0,
                error_budget_remaining=1.0,
                violated=False,
                window_hours=self.window_hours,
            )
        compliance = sum(1 for s in samples if s.success) / len(samples)
        error_budget = max(0.0, 1.0 - target_compliance)
        consumed = max(0.0, target_compliance - compliance)
        burn_rate = consumed / error_budget if error_budget > 0 else 0.0
        remaining = max(0.0, 1.0 - burn_rate)
        violated = compliance < target_compliance
        return SloEvaluation(
            name=slo,
            compliance_ratio=compliance,
            burn_rate=burn_rate,
            error_budget_remaining=remaining,
            violated=violated,
            window_hours=self.window_hours,
        )

    def evaluate_all(self) -> list[SloEvaluation]:
        return [self.evaluate(s) for s in SloName]

    def error_budget_summary(self) -> dict[str, Any]:
        evals = self.evaluate_all()
        violated = [e for e in evals if e.violated]
        return {
            "violated_count": len(violated),
            "slos": [e.to_dict() for e in evals],
            "critical_burn": max((e.burn_rate for e in evals), default=0.0),
        }

    def ingest_operational_signals(
        self,
        *,
        publish_latency_sec: float | None = None,
        cognition_sec: float | None = None,
        delivery_ok: bool | None = None,
        uptime_ok: bool = True,
        queue_depth: int = 0,
        operator_response_sec: float | None = None,
    ) -> None:
        if publish_latency_sec is not None:
            ok = publish_latency_sec <= _SLO_TARGETS[SloName.PUBLISH_LATENCY]["p99_sec"]
            self.record(SloName.PUBLISH_LATENCY, value=publish_latency_sec, success=ok)
        if cognition_sec is not None:
            ok = cognition_sec <= _SLO_TARGETS[SloName.COGNITION_LATENCY]["p99_sec"]
            self.record(SloName.COGNITION_LATENCY, value=cognition_sec, success=ok)
        if delivery_ok is not None:
            self.record(SloName.DELIVERY_SUCCESS, value=1.0 if delivery_ok else 0.0, success=delivery_ok)
        self.record(SloName.UPTIME, value=1.0 if uptime_ok else 0.0, success=uptime_ok)
        max_d = _SLO_TARGETS[SloName.QUEUE_DRAIN]["max_depth"]
        self.record(
            SloName.QUEUE_DRAIN,
            value=float(queue_depth),
            success=queue_depth <= max_d,
        )
        if operator_response_sec is not None:
            ok = operator_response_sec <= _SLO_TARGETS[SloName.OPERATOR_RESPONSE]["p99_sec"]
            self.record(SloName.OPERATOR_RESPONSE, value=operator_response_sec, success=ok)
