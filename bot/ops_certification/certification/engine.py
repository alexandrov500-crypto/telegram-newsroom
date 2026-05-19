from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class CertificationState(str, Enum):
    NOT_READY = "NOT_READY"
    CONDITIONAL = "CONDITIONAL"
    CERTIFIED = "CERTIFIED"
    LOCKED_DOWN = "LOCKED_DOWN"


@dataclass(frozen=True)
class CertificationCheck:
    check_id: str
    passed: bool
    detail: str


@dataclass
class CertificationResult:
    state: CertificationState
    score: float
    checks: tuple[CertificationCheck, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "score": round(self.score, 4),
            "blockers": list(self.blockers),
            "checks": [
                {"id": c.check_id, "passed": c.passed, "detail": c.detail}
                for c in self.checks
            ],
        }

    def summary_text(self) -> str:
        emoji = {
            CertificationState.CERTIFIED: "✅",
            CertificationState.CONDITIONAL: "🟡",
            CertificationState.NOT_READY: "⛔",
            CertificationState.LOCKED_DOWN: "🔒",
        }.get(self.state, "⚪")
        lines = [
            f"<b>{emoji} Certification</b> · <code>{self.state.value}</code>",
            f"Score: <b>{self.score:.0%}</b>",
        ]
        for c in self.checks:
            mark = "✓" if c.passed else "✗"
            lines.append(f"{mark} {c.check_id}: {c.detail[:60]}")
        if self.blockers:
            lines.append(f"\nBlockers: {', '.join(self.blockers[:6])}")
        return "\n".join(lines)


@dataclass
class ProductionCertificationEngine:
    """Formal go-live certification before FULL_PRODUCTION."""

    min_score: float = 0.85
    window_hours: float = 24.0

    def evaluate(
        self,
        *,
        fatal_incidents: int = 0,
        worker_stale: int = 0,
        worker_total: int = 0,
        replay_ok: bool = True,
        queue_depth: int = 0,
        recovery_ok: bool = True,
        budget_anomaly: bool = False,
        telegram_health: float = 1.0,
        event_bus_dlq: int = 0,
        event_bus_pending: int = 0,
        db_ok: bool = True,
        memory_trend_ok: bool = True,
        unbounded_retries: bool = False,
        poison_growth: int = 0,
        stability_score: float = 1.0,
        slo_violations: int = 0,
        locked_down: bool = False,
    ) -> CertificationResult:
        checks: list[CertificationCheck] = []

        def add(cid: str, passed: bool, detail: str) -> None:
            checks.append(CertificationCheck(cid, passed, detail))

        add("no_fatal_incidents", fatal_incidents == 0, f"fatal={fatal_incidents}")
        add(
            "worker_mesh",
            worker_total > 0 and worker_stale == 0,
            f"workers={worker_total} stale={worker_stale}",
        )
        add("replay_integrity", replay_ok, "replay verified" if replay_ok else "replay fail")
        add("queues_stable", queue_depth < 400, f"depth={queue_depth}")
        add("recovery_validated", recovery_ok, "recovery ok" if recovery_ok else "recovery issues")
        add("budget_stable", not budget_anomaly, "budget anomaly" if budget_anomaly else "ok")
        add("telegram_delivery", telegram_health >= 0.9, f"health={telegram_health:.2f}")
        add(
            "event_bus",
            event_bus_dlq < 50 and event_bus_pending < 500,
            f"pending={event_bus_pending} dlq={event_bus_dlq}",
        )
        add("db_healthy", db_ok, "primary db ping")
        add("memory_trend", memory_trend_ok, "memory drift acceptable")
        add("retry_bounded", not unbounded_retries, "retries bounded")
        add("poison_queue", poison_growth < 20, f"poison_delta={poison_growth}")
        add("stability", stability_score >= 0.65, f"score={stability_score:.2f}")
        add("slo_compliance", slo_violations == 0, f"violations={slo_violations}")

        passed_count = sum(1 for c in checks if c.passed)
        score = passed_count / len(checks) if checks else 0.0
        blockers = [c.check_id for c in checks if not c.passed]

        if locked_down:
            state = CertificationState.LOCKED_DOWN
        elif fatal_incidents > 0 or "no_fatal_incidents" in blockers:
            state = CertificationState.NOT_READY
        elif score >= self.min_score and not blockers:
            state = CertificationState.CERTIFIED
        elif score >= 0.7:
            state = CertificationState.CONDITIONAL
        else:
            state = CertificationState.NOT_READY

        return CertificationResult(
            state=state,
            score=score,
            checks=tuple(checks),
            blockers=tuple(blockers),
        )

    def certify_if_ready(
        self,
        result: CertificationResult,
        *,
        persist: Callable[[CertificationResult], None] | None = None,
    ) -> CertificationResult:
        if persist is not None:
            persist(result)
        return result
