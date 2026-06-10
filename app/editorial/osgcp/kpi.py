"""OSGCP health KPI snapshot."""

from __future__ import annotations

from typing import Any

from app.editorial.osgcp.config import osgcp_enabled
from app.editorial.osgcp.kpi_loop import compute_editorial_kpi_state
from app.editorial.osgcp.state import osgcp_snapshot


def osgcp_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    return {
        "enabled": osgcp_enabled(),
        "osgcp_state": osgcp_snapshot(runtime_dir),
        "kpi_loop": compute_editorial_kpi_state(runtime_dir).to_dict(),
        "objective": "adaptive_cognitive_information_os_continuous_flow",
    }
