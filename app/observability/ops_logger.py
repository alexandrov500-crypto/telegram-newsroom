"""Structured OPS control-plane change logging."""

from __future__ import annotations

import logging

logger = logging.getLogger("ops.control_plane")


def log_ops_change(field: str, value: object, *, reason: str) -> None:
    logger.info("[OPS] %s=%s reason=%s", field, value, reason[:300])
