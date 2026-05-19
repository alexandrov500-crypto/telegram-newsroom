from __future__ import annotations

from typing import Any

from bot.ops_consolidation.contracts import subsystem_contracts
from bot.ops_consolidation.loops import inventory_background_loops
from bot.ops_consolidation.operator_surface import operator_surface_audit
from bot.ops_consolidation.persistence import persistence_audit
from bot.ops_consolidation.signals import OVERLAP_GROUPS
from bot.ops_consolidation.telemetry import telemetry_tiering_report
from pathlib import Path


def compute_complexity_metrics(db_path: Path) -> dict[str, Any]:
    loops = inventory_background_loops()
    telemetry = telemetry_tiering_report()
    surface = operator_surface_audit()
    persistence = persistence_audit(db_path)
    contracts = subsystem_contracts()

    loop_count = loops["count"]
    alert_categories = len(OVERLAP_GROUPS) + len(telemetry["by_tier"].get("critical", []))
    telemetry_streams = len(telemetry["registry"])
    table_count = persistence["ops_table_count"]
    operator_surfaces = surface["total_commands"]
    subsystem_count = len(contracts)

    # Normalized complexity score 0–1 (higher = more complex)
    score = min(
        1.0,
        loop_count * 0.04
        + subsystem_count * 0.03
        + table_count * 0.008
        + operator_surfaces * 0.015
        + alert_categories * 0.02,
    )

    band = "low"
    if score >= 0.65:
        band = "high"
    elif score >= 0.4:
        band = "moderate"

    return {
        "complexity_score": round(score, 3),
        "complexity_band": band,
        "background_loop_count": loop_count,
        "subsystem_contract_count": subsystem_count,
        "alert_overlap_groups": len(OVERLAP_GROUPS),
        "telemetry_stream_count": telemetry_streams,
        "ops_table_count": table_count,
        "operator_command_count": operator_surfaces,
        "operator_primary_commands": surface["primary_count"],
        "critical_telemetry_count": len(telemetry["by_tier"].get("critical", [])),
        "moving_parts_estimate": loop_count + subsystem_count,
    }
