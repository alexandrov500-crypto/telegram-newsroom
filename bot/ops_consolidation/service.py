from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bot.ops_consolidation.report import build_consolidation_html, build_consolidation_report
from bot.ops_consolidation.signals import dedupe_context_signals
from bot.ops_consolidation.stability import architecture_stability_phase_enabled
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("OPS_CONSOLIDATION_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _dedupe_enabled() -> bool:
    raw = os.getenv("OPS_CONSOLIDATION_DEDUPE", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def consolidation_payload(*, db_path: Path | None = None, persist: bool = True) -> dict[str, Any]:
    if not _enabled():
        return {"status": "disabled"}
    path = init_database(db_path or default_db_path())
    snap = build_consolidation_report(path, persist=persist)
    return {"status": "ok", **snap}


def consolidation_html(*, db_path: Path | None = None) -> str:
    payload = consolidation_payload(db_path=db_path)
    if payload.get("status") == "disabled":
        return "<b>Consolidation</b>\n\nDisabled (OPS_CONSOLIDATION_ENABLED=false)."
    return build_consolidation_html(payload)


def maybe_dedupe_operator_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Apply signal dedupe when consolidation dedupe flag is on."""
    if not _dedupe_enabled():
        return ctx
    try:
        return dedupe_context_signals(ctx)
    except Exception:
        logger.debug("event=consolidation_dedupe_failed")
        return ctx


def consolidation_status_summary() -> dict[str, Any]:
    return {
        "consolidation_enabled": _enabled(),
        "dedupe_enabled": _dedupe_enabled(),
        "stability_phase": architecture_stability_phase_enabled(),
    }
