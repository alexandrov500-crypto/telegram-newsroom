"""Collect RELEASE_CONTRACT checks from runtime (single integration point)."""

from __future__ import annotations

from typing import Any


def collect_contract_checks(runtime_dir: str) -> dict[str, Any]:
    from app.observability.final_stability_report import build_final_stability_report

    report = build_final_stability_report(runtime_dir)
    return {
        "required_checks": list(report.get("required_checks") or []),
        "observational_checks": list(report.get("observational_checks") or []),
        "validation_environment": report.get("validation_environment"),
        "execution_graph_consistency": report.get("execution_graph_consistency"),
        "blockers": list(report.get("blockers") or []),
        "warnings": list(report.get("warnings") or []),
        "verdict": report.get("FINAL_STABILITY_VERDICT"),
    }
