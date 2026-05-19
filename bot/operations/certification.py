from __future__ import annotations

import uuid
from typing import Any

from bot.chaos.runner import run_chaos_suite
from bot.operations.repository import OperationsRepository
from bot.operations.types import CertificationGate, CertificationReport, ProductionSLOs


class ProductionReadinessCertification:
    """Automated certification gates before production promotion."""

    def __init__(self, repository: OperationsRepository, slos: ProductionSLOs | None = None) -> None:
        self._repo = repository
        self._slos = slos or ProductionSLOs()

    async def run(
        self,
        *,
        signals: dict[str, Any],
        chaos_components: dict[str, Any] | None = None,
    ) -> CertificationReport:
        run_id = str(uuid.uuid4())[:12]
        gates: list[CertificationGate] = []

        backlog = int(signals.get("queue_backlog", 0))
        gates.append(
            CertificationGate(
                "operational_backlog",
                "Editorial queue backlog",
                backlog <= self._slos.queue_backlog_max,
                f"backlog={backlog}",
                float(backlog),
                float(self._slos.queue_backlog_max),
            )
        )

        epistemic = float(signals.get("epistemic_stability", 1.0))
        gates.append(
            CertificationGate(
                "epistemic_stability",
                "Epistemic stability",
                epistemic >= self._slos.epistemic_stability_min,
                f"stability={epistemic:.3f}",
                epistemic,
                self._slos.epistemic_stability_min,
            )
        )

        mesh_h = float(signals.get("mesh_health", 1.0))
        gates.append(
            CertificationGate(
                "federation_stability",
                "Mesh health",
                mesh_h >= self._slos.mesh_health_min,
                f"mesh={mesh_h:.3f}",
                mesh_h,
                self._slos.mesh_health_min,
            )
        )

        replay_div = float(signals.get("replay_divergence", 0.0))
        gates.append(
            CertificationGate(
                "replay_integrity",
                "Replay divergence",
                replay_div <= self._slos.replay_divergence_max,
                f"divergence={replay_div:.3f}",
                replay_div,
                self._slos.replay_divergence_max,
            )
        )

        storage_growth = float(signals.get("storage_growth_mb_day", 0.0))
        gates.append(
            CertificationGate(
                "storage_sustainability",
                "Storage growth",
                storage_growth <= self._slos.storage_growth_mb_per_day_max,
                f"growth={storage_growth:.1f}MB/day",
                storage_growth,
                self._slos.storage_growth_mb_per_day_max,
            )
        )

        if chaos_components and all(
            chaos_components.get(k) is not None
            for k in ("recovery", "idempotency", "scheduler", "degradation", "coordination")
        ):
            try:
                results = await run_chaos_suite(**chaos_components)  # type: ignore[arg-type]
                chaos_ok = all(r.passed for r in results)
                gates.append(
                    CertificationGate(
                        "chaos_validation",
                        "Chaos suite",
                        chaos_ok,
                        f"{sum(1 for r in results if r.passed)}/{len(results)} passed",
                    )
                )
            except Exception as exc:
                gates.append(
                    CertificationGate(
                        "chaos_validation",
                        "Chaos suite",
                        False,
                        str(exc)[:200],
                    )
                )

        passed = all(g.passed for g in gates)
        report = CertificationReport(
            run_id=run_id,
            passed=passed,
            gates=gates,
            summary=f"{'CERTIFIED' if passed else 'NOT CERTIFIED'}: {sum(1 for g in gates if g.passed)}/{len(gates)} gates",
        )
        self._repo.save_certification(
            run_id,
            passed=passed,
            gates=[
                {
                    "gate_id": g.gate_id,
                    "name": g.name,
                    "passed": g.passed,
                    "detail": g.detail,
                    "value": g.value,
                    "threshold": g.threshold,
                }
                for g in gates
            ],
        )
        try:
            from bot.observability.metrics import set_certification_status

            set_certification_status(passed)
        except Exception:
            pass
        return report
