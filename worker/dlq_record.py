"""Structured dead-letter records (Redis + in-memory transport)."""

from __future__ import annotations

import time
from typing import Any

SCHEMA_VERSION = 1


def build_dlq_record(
    *,
    kind: str,
    delivery_id: str,
    reason: str,
    original: str,
    dlq_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dead_lettered_at": time.time(),
        "kind": kind,
        "delivery_id": delivery_id,
        "reason": reason[:8000],
        "original": original[:500_000],
    }
    if dlq_meta:
        for k, v in dlq_meta.items():
            if k in merged and k != "reason":
                continue
            merged[k] = v
    return merged
