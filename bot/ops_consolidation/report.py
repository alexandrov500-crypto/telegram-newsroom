from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.ops_consolidation.burden import estimate_maintenance_burden
from bot.ops_consolidation.contracts import subsystem_contracts
from bot.ops_consolidation.loops import inventory_background_loops
from bot.ops_consolidation.metrics import compute_complexity_metrics
from bot.ops_consolidation.operator_surface import operator_surface_audit
from bot.ops_consolidation.persistence import persistence_audit
from bot.ops_consolidation.repository import ConsolidationRepository
from bot.ops_consolidation.signals import analyze_signal_overlap
from bot.ops_consolidation.stability import stability_snapshot
from bot.ops_consolidation.telemetry import telemetry_tiering_report
from bot.storage.db import init_database


def build_consolidation_report(db_path: Path, *, persist: bool = True) -> dict[str, Any]:
    path = init_database(db_path)
    contracts = subsystem_contracts()
    signals = analyze_signal_overlap()
    loops = inventory_background_loops()
    telemetry = telemetry_tiering_report()
    persistence = persistence_audit(path)
    surface = operator_surface_audit()
    complexity = compute_complexity_metrics(path)
    burden = estimate_maintenance_burden(
        complexity=complexity,
        persistence=persistence,
        loops=loops,
        signals=signals,
    )
    stability = stability_snapshot()

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stability_phase": stability,
        "subsystem_contracts": contracts,
        "signal_overlap": signals,
        "background_loops": loops,
        "telemetry_tiering": telemetry,
        "persistence_ownership": persistence,
        "operator_surface": surface,
        "complexity_metrics": complexity,
        "maintenance_burden": burden,
        "consolidation_actions": _consolidation_actions(complexity, burden, signals, loops),
    }

    if persist:
        try:
            day = datetime.now(timezone.utc).date().isoformat()
            ConsolidationRepository(path).save_snapshot(
                day,
                report,
                float(complexity["complexity_score"]),
            )
        except Exception:
            pass

    return report


def _consolidation_actions(
    complexity: dict[str, Any],
    burden: dict[str, Any],
    signals: dict[str, Any],
    loops: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    actions.extend(signals.get("consolidation_recommendations") or [])
    actions.extend(loops.get("rationalization_recommendations") or [])
    actions.extend(burden.get("top_reduction_levers") or [])
    if complexity.get("complexity_band") == "high":
        actions.append("Enable ARCHITECTURE_STABILITY_PHASE=true before adding subsystems")
    actions.append("Use primary operator workflow: digest → resilience → weekly review")
    return list(dict.fromkeys(actions))[:12]


def build_consolidation_html(report: dict[str, Any]) -> str:
    cm = report.get("complexity_metrics") or {}
    burden = report.get("maintenance_burden") or {}
    stability = report.get("stability_phase") or {}
    surface = report.get("operator_surface") or {}

    lines = [
        "<b>Operational consolidation</b>",
        f"<i>{html.escape(str(report.get('generated_at', ''))[:19])} UTC</i>",
        "",
        "<b>Complexity</b>",
        f"Score {float(cm.get('complexity_score', 0)):.2f} "
        f"(<code>{html.escape(str(cm.get('complexity_band', '?')))}</code>) · "
        f"loops {cm.get('background_loop_count')} · ops tables {cm.get('ops_table_count')}",
        "",
        "<b>Maintenance burden</b>",
        f"{html.escape(str(burden.get('sustainability', '?')))} "
        f"(score {burden.get('overall_burden_score')})",
        "",
        "<b>Stability phase</b>",
        f"{'ON' if stability.get('enabled') else 'OFF'} — "
        f"<code>ARCHITECTURE_STABILITY_PHASE</code>",
        "",
        "<b>Operator workflow (primary)</b>",
    ]
    for step in surface.get("primary_workflow") or []:
        lines.append(f"• {html.escape(step)}")

    overlaps = (report.get("signal_overlap") or {}).get("overlap_groups") or []
    if overlaps:
        lines.extend(["", "<b>Signal overlap (dedupe targets)</b>"])
        for g in overlaps[:4]:
            lines.append(f"• {html.escape(str(g.get('concern', '?')))} → {html.escape(str(g.get('canonical', '')))}")

    actions = report.get("consolidation_actions") or []
    if actions:
        lines.extend(["", "<b>Recommended actions</b>"])
        for a in actions[:6]:
            lines.append(f"• {html.escape(a)}")

    return "\n".join(lines)
