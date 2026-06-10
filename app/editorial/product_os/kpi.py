"""PEOS KPI snapshot for /health."""

from __future__ import annotations

from typing import Any

from app.editorial.product_os.config import product_os_enabled
from app.editorial.product_os.state import product_os_snapshot


def product_os_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, Any]:
    snap = product_os_snapshot(runtime_dir)
    return {
        "enabled": product_os_enabled(),
        "product_os": snap,
        "objective": snap.get("objective"),
    }
