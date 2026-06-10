"""EAA v2 KPI snapshot."""

from __future__ import annotations

from app.editorial.eaa.config import zero_human_mode
from app.editorial.eaa.state import eaa_snapshot


def eaa_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, object]:
    return {
        **eaa_snapshot(runtime_dir),
        "zero_human_mode_enabled": zero_human_mode(),
        "core_kpis": {
            "autonomous_publish_rate": "eaa_decision_matrix",
            "safety_envelope_pass_rate": "safety_envelope",
            "zero_human_ratio": "eaa_state",
        },
    }
