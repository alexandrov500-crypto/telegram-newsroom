from __future__ import annotations

from dataclasses import dataclass

from bot.operations.startup_validation import StartupValidationRunner


@dataclass(frozen=True)
class StagingCheck:
    name: str
    passed: bool
    detail: str


class StagingRuntimeValidator:
    """Startup dependency validation and smoke checks (delegates to unified runner)."""

    def run_all(self) -> list[StagingCheck]:
        report = StartupValidationRunner.run_smoke()
        return [
            StagingCheck(c.check_id, c.passed, c.detail)
            for c in report.checks
        ]

    def smoke_report(self) -> str:
        report = StartupValidationRunner.run_smoke()
        return report.operator_summary()
