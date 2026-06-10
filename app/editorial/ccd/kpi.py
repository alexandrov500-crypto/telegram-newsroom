"""CCD KPI snapshot."""

from __future__ import annotations

from typing import Any

from app.editorial.ccd.config import ccd_enabled
from app.editorial.ccd.state import ccd_snapshot


def ccd_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    return {
        "enabled": ccd_enabled(),
        "ccd_state": ccd_snapshot(runtime_dir),
        "objective": "weekly_cognitive_experience_engine",
    }
