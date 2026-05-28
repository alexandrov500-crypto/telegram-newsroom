"""Global execution authority map — validates call origin before protected pipeline code runs."""

from __future__ import annotations

import inspect
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class EnforcementMode(str, Enum):
    ADVISORY = "advisory"
    STRICT = "strict"


# Only these may start protected pipeline work.
ALLOWED_ENTRYPOINTS = frozenset(
    {
        "execute_pipeline_step",
        "execute_pipeline_step_async",
        "execute_pipeline_publish",
        "_run_wrapped_pipeline_coroutine",
    }
)

# Frames that may appear between entrypoint and *_impl (wrapper internals).
ALLOWED_WRAPPER_INTERNALS = frozenset(
    {
        "execute_pipeline_step",
        "execute_pipeline_step_async",
        "execute_pipeline_publish",
        "_run_wrapped_pipeline_coroutine",
        "_execute_with_contract",
    }
)

REGISTERED_EXECUTION_POINTS = frozenset(
    {
        "collect",
        "summarize",
        "publish",
        "minimal_draft",
        "scheduled_publish",
    }
)

FORBIDDEN_DIRECT_CALLS = frozenset(
    {
        "_summarize_step_impl",
        "_scheduled_publish_step_impl",
        "_execute_admin_publication_flow_impl",
        "_try_minimal_draft_from_raw_impl",
    }
)

# impl symbol -> host module suffix (only this file may reference the symbol in AST calls).
IMPL_HOST_SUFFIX = {
    "_summarize_step_impl": "scheduler/jobs.py",
    "_scheduled_publish_step_impl": "scheduler/jobs.py",
    "_execute_admin_publication_flow_impl": "publisher/publish_service.py",
    "_try_minimal_draft_from_raw_impl": "app/recovery/minimal_draft.py",
}

# Tests may call entrypoints directly.
ALLOWED_CALLER_PREFIXES = (
    "tests/",
    "test_",
)


@dataclass(frozen=True, slots=True)
class ExecutionOriginVerdict:
    allowed: bool
    reason: str
    entry_frame: str | None
    callee: str


def runtime_enforcement_mode() -> EnforcementMode:
    raw = os.getenv("PIPELINE_EXECUTION_ENFORCEMENT", "advisory").strip().lower()
    if raw in {"strict", "hard", "true", "1"}:
        return EnforcementMode.STRICT
    if os.getenv("PIPELINE_BYPASS_STRICT", "").strip().lower() in {"1", "true", "yes", "on"}:
        return EnforcementMode.STRICT
    return EnforcementMode.ADVISORY


def validate_execution_origin(
    callee: str,
    *,
    stack: list[inspect.FrameInfo] | None = None,
) -> ExecutionOriginVerdict:
    """
    Inspect stack: protected impl must be reached from allowed entrypoints only.
    """
    if stack is None:
        stack = list(inspect.stack())[1:]

    entry_frame: str | None = None
    for frame in stack:
        func = frame.function
        filename = frame.filename.replace("\\", "/")
        if any(filename.endswith(p) for p in ALLOWED_CALLER_PREFIXES if "/" in p):
            return ExecutionOriginVerdict(
                allowed=True,
                reason="test_harness",
                entry_frame=func,
                callee=callee,
            )
        if func in ALLOWED_ENTRYPOINTS or func in ALLOWED_WRAPPER_INTERNALS:
            entry_frame = entry_frame or func
        if func == callee or func.endswith("_impl") and callee in func:
            if entry_frame:
                return ExecutionOriginVerdict(
                    allowed=True,
                    reason=f"via_{entry_frame}",
                    entry_frame=entry_frame,
                    callee=callee,
                )

    if _wrapper_depth_from_stack(stack) > 0:
        return ExecutionOriginVerdict(
            allowed=True,
            reason="wrapper_depth_context",
            entry_frame=entry_frame,
            callee=callee,
        )

    return ExecutionOriginVerdict(
        allowed=False,
        reason="no_allowed_entrypoint_in_stack",
        entry_frame=entry_frame,
        callee=callee,
    )


def _wrapper_depth_from_stack(stack: list[inspect.FrameInfo]) -> int:
    depth = 0
    for frame in stack:
        if frame.function in ALLOWED_ENTRYPOINTS | ALLOWED_WRAPPER_INTERNALS:
            depth += 1
    return depth


def enforce_execution_origin(callee: str) -> ExecutionOriginVerdict:
    """Log CRITICAL and optionally raise on bypass attempt."""
    verdict = validate_execution_origin(callee)
    if verdict.allowed:
        return verdict

    log_event(
        logger,
        "CRITICAL_EXECUTION_BYPASS_ATTEMPT",
        callee=callee,
        reason=verdict.reason,
        enforcement=runtime_enforcement_mode().value,
        entry_frame=verdict.entry_frame,
    )
    if runtime_enforcement_mode() == EnforcementMode.STRICT:
        raise RuntimeError(
            f"PIPELINE BYPASS DETECTED: {callee} — {verdict.reason} "
            f"(use execute_pipeline_step / execute_pipeline_step_async only)"
        )
    logger.critical(
        "CRITICAL_EXECUTION_BYPASS_ATTEMPT callee=%s reason=%s",
        callee,
        verdict.reason,
    )
    return verdict


def is_forbidden_impl_symbol(name: str) -> bool:
    return name in FORBIDDEN_DIRECT_CALLS
