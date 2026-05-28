"""Unified launch control and deterministic safety precedence."""

from __future__ import annotations

import os
from typing import Any


def _b(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def launch_state() -> dict[str, Any]:
    return {
        "PREPUBLIC_QA_MODE": _b("PREPUBLIC_QA_MODE"),
        "CONTROLLED_PUBLIC_ROLLOUT": _b("CONTROLLED_PUBLIC_ROLLOUT"),
        "LIVE_ROLLBACK_MODE": _b("LIVE_ROLLBACK_MODE"),
        "AUTO_PUBLISH_ENABLED": _b("AUTO_PUBLISH_ENABLED"),
        "ROLLOUT_STAGE": os.getenv("ROLLOUT_STAGE", "STAGE_0_PRIVATE_QA").strip(),
    }


def validate_launch_state() -> tuple[bool, list[str]]:
    st = launch_state()
    errs: list[str] = []
    if st["LIVE_ROLLBACK_MODE"] and st["AUTO_PUBLISH_ENABLED"]:
        errs.append("rollback_conflicts_with_auto_publish")
    if st["CONTROLLED_PUBLIC_ROLLOUT"] and not str(st["ROLLOUT_STAGE"]).startswith("STAGE_"):
        errs.append("invalid_rollout_stage")
    if st["PREPUBLIC_QA_MODE"] and st["ROLLOUT_STAGE"] == "STAGE_3_FULL_AUTONOMOUS":
        errs.append("qa_mode_conflicts_with_full_autonomous_stage")
    return len(errs) == 0, errs


def enforce_launch_safety() -> dict[str, Any]:
    ok, errs = validate_launch_state()
    state = launch_state()
    # precedence: rollback > incident freeze > rollout > auto publish.
    effective_auto_publish = bool(state["AUTO_PUBLISH_ENABLED"]) and not bool(state["LIVE_ROLLBACK_MODE"])
    return {
        "valid": ok,
        "errors": errs,
        "state": state,
        "effective_auto_publish": effective_auto_publish,
    }
