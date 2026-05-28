"""Env-driven recovery overrides — restore raw → draft → publish without deleting gates."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.openai_circuit import OpenAICircuit

logger = logging.getLogger(__name__)


def _env_on(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def is_force_ai_pipeline_enabled() -> bool:
    return _env_on("FORCE_AI_PIPELINE_ENABLED")


def is_minimal_pipeline_mode() -> bool:
    return _env_on("MINIMAL_PIPELINE_MODE") or _env_on("MINIMAL_NEWSROOM_MODE")


def is_force_publish_bypass() -> bool:
    return _env_on("FORCE_PUBLISH_BYPASS")


def recovery_bypass_active() -> bool:
    return (
        is_force_ai_pipeline_enabled()
        or is_minimal_pipeline_mode()
        or is_force_publish_bypass()
    )


def upstream_pipeline_state(*, ctx_ai_enabled: bool, circuit_allows: bool) -> str:
    if is_force_ai_pipeline_enabled():
        return "forced"
    if ctx_ai_enabled and circuit_allows:
        return "normal"
    return "disabled"


def effective_ai_gate_open(*, ctx_ai_enabled: bool, circuit: OpenAICircuit) -> bool:
    try:
        from app.recovery.pipeline_context_builder import build_pipeline_decision_context
        from app.state.pipeline_decision_engine import make_pipeline_decision

        return make_pipeline_decision(build_pipeline_decision_context()).ai_gate_open
    except Exception:
        pass
    if is_force_ai_pipeline_enabled() or is_minimal_pipeline_mode():
        return True
    return bool(ctx_ai_enabled and circuit.allow_request())


def log_upstream_pipeline_state(
    *,
    ctx_ai_enabled: bool,
    circuit_allows: bool,
    ai_gate_open: bool,
) -> None:
    state = upstream_pipeline_state(
        ctx_ai_enabled=ctx_ai_enabled,
        circuit_allows=circuit_allows,
    )
    try:
        from utils.structured_log import log_event

        log_event(
            logger,
            "UPSTREAM_PIPELINE_STATE",
            state=state,
            ctx_ai_enabled=ctx_ai_enabled,
            circuit_allows=circuit_allows,
            ai_gate_open=ai_gate_open,
            force_ai=is_force_ai_pipeline_enabled(),
            minimal_mode=is_minimal_pipeline_mode(),
            force_publish_bypass=is_force_publish_bypass(),
        )
    except Exception:
        logger.info(
            "UPSTREAM_PIPELINE_STATE state=%s ai_gate_open=%s",
            state,
            ai_gate_open,
        )
