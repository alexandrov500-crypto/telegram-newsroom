"""Read-only editorial / intelligence slice for dashboards."""

from __future__ import annotations

from typing import Any

from app.config import Settings


def build_editorial_dashboard(settings: Settings) -> dict[str, Any]:
    """Sync aggregation (reuses editorial intelligence report builder)."""
    from utils.editorial_intelligence_report import build_editorial_intelligence_report

    return build_editorial_intelligence_report(settings)
