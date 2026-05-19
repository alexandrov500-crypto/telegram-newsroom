from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bot.operations.burnin import BurnInRunner
from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class BurnInSummary:
    run_id: str
    period: str
    health_mean: float
    epistemic_mean: float
    regressions: tuple[str, ...]
    markdown: str


class BurnInReportGenerator:
    """Rolling burn-in reports and regression alerts."""

    def __init__(self, repository: OperationsRepository, runner: BurnInRunner) -> None:
        self._repo = repository
        self._runner = runner

    def generate_operational_report(self, run_id: str, *, period: str = "24h") -> BurnInSummary:
        """Full staging burn-in evidence report for operators."""
        baseline = self._runner.analyze_baseline(run_id)
        md = self._to_operational_markdown(run_id, period, baseline)
        summary = BurnInSummary(
            run_id=run_id,
            period=period,
            health_mean=baseline.health_mean,
            epistemic_mean=baseline.epistemic_stability_mean,
            regressions=tuple(baseline.regressions),
            markdown=md,
        )
        self._repo.save_burnin_report(
            run_id=run_id,
            period=period,
            markdown=md,
            regressions=list(baseline.regressions),
            health_score=baseline.health_mean,
        )
        return summary

    def generate_period_report(self, run_id: str, *, period: str = "rolling") -> BurnInSummary:
        baseline = self._runner.analyze_baseline(run_id)
        md = self._to_markdown(run_id, period, baseline)
        self._repo.save_burnin_report(
            run_id=run_id,
            period=period,
            markdown=md,
            regressions=list(baseline.regressions),
            health_score=baseline.health_mean,
        )
        if baseline.regressions:
            self._repo.enqueue_alert(
                alert_key=f"burnin:regression:{run_id}",
                category="info",
                title=f"Burn-in regression detected ({period})",
                priority=75,
                detail={"regressions": baseline.regressions},
            )
        return BurnInSummary(
            run_id=run_id,
            period=period,
            health_mean=baseline.health_mean,
            epistemic_mean=baseline.epistemic_stability_mean,
            regressions=tuple(baseline.regressions),
            markdown=md,
        )

    def write_report_file(self, summary: BurnInSummary, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Burn-in report — {summary.period}\n\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
        )
        path.write_text(header + summary.markdown, encoding="utf-8")
        return path

    @staticmethod
    def _to_markdown(run_id: str, period: str, baseline) -> str:
        lines = [
            f"## Run `{run_id}` ({period})",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Samples | {baseline.samples} |",
            f"| Health mean | {baseline.health_mean:.3f} |",
            f"| Health min | {baseline.health_min:.3f} |",
            f"| Backlog mean | {baseline.backlog_mean:.1f} |",
            f"| Epistemic stability mean | {baseline.epistemic_stability_mean:.3f} |",
            "",
        ]
        if baseline.regressions:
            lines.append("### Regressions")
            for r in baseline.regressions:
                lines.append(f"- {r}")
        else:
            lines.append("No regressions detected.")
        return "\n".join(lines)

    def _to_operational_markdown(self, run_id: str, period: str, baseline) -> str:
        lines = [
            f"## Operational burn-in `{run_id}` ({period})",
            "",
            "### Core metrics",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Samples | {baseline.samples} |",
            f"| Health mean | {baseline.health_mean:.3f} |",
            f"| Health min | {baseline.health_min:.3f} |",
            f"| Backlog mean | {baseline.backlog_mean:.1f} |",
            f"| Epistemic stability mean | {baseline.epistemic_stability_mean:.3f} |",
            "",
            "### Incidents & operator load",
            "",
            f"| Signal | Count |",
            f"|--------|-------|",
            f"| Incident bundles | {self._repo.incident_bundle_count()} |",
            f"| Operator sessions completed | {self._repo.operator_intervention_count()} |",
            f"| Staging publish audits | {self._repo.staging_publish_audit_count()} |",
            "",
            "### Epistemic state",
            "",
            f"| Signal | Count |",
            f"|--------|-------|",
            f"| Open contradictions | {self._repo.open_contradiction_count()} |",
            f"| Misinformation alerts (pending) | {self._repo.pending_misinfo_alert_count()} |",
            "",
            "### Storage & replay",
            "",
        ]
        counts = self._repo.table_row_counts()
        lines.append(f"- Total DB rows (tracked tables): {sum(counts.values())}")
        lines.append(f"- `sourced_event_log`: {counts.get('sourced_event_log', 0)}")
        lines.append(f"- `mesh_cognitive_events`: {counts.get('mesh_cognitive_events', 0)}")
        feeds = self._repo.feed_health_report()
        if feeds:
            unreliable = sum(1 for f in feeds if float(f.get("reliability_score", 1)) < 0.4)
            lines.append(f"- Unreliable feeds: {unreliable}/{len(feeds)}")
        if baseline.regressions:
            lines.append("")
            lines.append("### Regressions")
            for r in baseline.regressions:
                lines.append(f"- {r}")
        else:
            lines.append("")
            lines.append("No regressions detected in burn-in window.")
        return "\n".join(lines)

    def write_full_report(self, summary: BurnInSummary, path: Path | None = None) -> Path:
        """Write to docs/BURN_IN_REPORT.md (operator evidence)."""
        target = path or Path("docs") / "BURN_IN_REPORT.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Burn-in operational report — {summary.period}\n\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"> Shadow-production staging evidence. Publishing remains operator-gated.\n\n"
        )
        target.write_text(header + summary.markdown, encoding="utf-8")
        return target
