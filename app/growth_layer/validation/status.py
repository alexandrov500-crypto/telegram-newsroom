"""Validation lifecycle status for post_growth_validation."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ValidationStatus(str, Enum):
    PENDING = "PENDING"
    T6_READY = "T6_READY"
    T24_READY = "T24_READY"
    FINAL = "FINAL"


_SNAPSHOT_TO_STATUS = {
    "t6h": ValidationStatus.T6_READY,
    "t24h": ValidationStatus.FINAL,
}


def status_for_snapshot(snapshot_label: str) -> ValidationStatus | None:
    return _SNAPSHOT_TO_STATUS.get(str(snapshot_label or "").strip())


def is_final_row(row: dict[str, Any]) -> bool:
    status = str(row.get("validation_status") or "")
    if status == ValidationStatus.FINAL.value:
        return True
    if status:
        return False
    return str(row.get("snapshot_label") or "") == "t24h" and row.get("actual_engagement") is not None


def filter_final_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if is_final_row(r)]
