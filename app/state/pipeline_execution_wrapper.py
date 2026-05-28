"""
Mandatory execution kernel — all pipeline steps must run through execute_pipeline_step.

Direct calls to protected implementations without the wrapper are bypass violations.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, TypeVar

from app.state.pipeline_execution_registry import (
    enforce_execution_origin,
    runtime_enforcement_mode,
    validate_execution_origin,
)
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

T = TypeVar("T")

_wrapper_depth: ContextVar[int] = ContextVar("pipeline_wrapper_depth", default=0)
_current_step: ContextVar[str] = ContextVar("pipeline_wrapper_step", default="")
_evaluation_only: ContextVar[bool] = ContextVar("pipeline_evaluation_only", default=False)
_trace_id: ContextVar[str] = ContextVar("pipeline_trace_id", default="")
_decision_engine_called: ContextVar[bool] = ContextVar("pipeline_decision_engine_called", default=False)
_wrapper_entry_logged: ContextVar[bool] = ContextVar("pipeline_wrapper_entry_logged", default=False)


@dataclass(frozen=True, slots=True)
class PipelineStepResult:
    """Explicit outcome — never silent None without reason."""

    value: Any | None
    outcome: str
    trace_id: str
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome in {"ok", "blocked", "explicit_reject"}


def _bypass_strict() -> bool:
    return runtime_enforcement_mode().value == "strict"


def wrapper_depth() -> int:
    return _wrapper_depth.get()


def current_pipeline_step() -> str:
    return _current_step.get()


def current_trace_id() -> str:
    return _trace_id.get()


@contextmanager
def pipeline_evaluation_only():
    """Health/startup: evaluate decision without executing protected steps."""
    tok = _evaluation_only.set(True)
    try:
        yield
    finally:
        _evaluation_only.reset(tok)


def require_pipeline_wrapper_active(callee: str) -> None:
    """
    Stack + depth enforcement before protected impl body runs.
    """
    if _evaluation_only.get():
        return
    if _wrapper_depth.get() > 0:
        enforce_execution_origin(callee)
        return
    enforce_execution_origin(callee)


def _log_execution_trace(
    *,
    phase: str,
    step_name: str,
    decision: Any,
    trace_id: str,
    executed_function: str | None = None,
    final_result: str | None = None,
    use_fallback: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if phase == "wrapper_entry":
        _wrapper_entry_logged.set(True)
    log_event(
        logger,
        "PIPELINE_EXECUTION_TRACE",
        phase=phase,
        step=step_name,
        trace_id=trace_id,
        decision_engine_output=decision.to_dict() if hasattr(decision, "to_dict") else decision,
        decision_engine_called=_decision_engine_called.get(),
        executed_function=executed_function,
        final_result=final_result,
        use_fallback=use_fallback,
        wrapper_depth=_wrapper_depth.get(),
        enforcement_mode=runtime_enforcement_mode().value,
        extra=extra or {},
    )


def _validate_execution_contract(
    *,
    step_name: str,
    trace_id: str,
    final_result: str | None,
    fn_executed: bool,
) -> None:
    missing: list[str] = []
    if not _decision_engine_called.get():
        missing.append("decision_engine_called")
    if not _wrapper_entry_logged.get():
        missing.append("wrapper_entry")
    if not trace_id:
        missing.append("trace_id")
    if fn_executed and final_result is None:
        missing.append("final_result")
    if missing:
        log_event(
            logger,
            "PIPELINE_FATAL_BYPASS_DETECTED",
            step=step_name,
            trace_id=trace_id,
            missing=missing,
            enforcement=runtime_enforcement_mode().value,
        )
        if _bypass_strict():
            raise RuntimeError(f"PIPELINE_FATAL_BYPASS_DETECTED: missing {missing}")


async def execute_pipeline_step(
    ctx: Any | None,
    step_name: str,
    fn: Callable[[], Awaitable[T]],
    *,
    require_should_execute: bool = True,
    skip_reason_attr: str = "tick_summarize_idle_reason",
) -> T | None:
    """Sync/async unified entry — sole authorized execution surface."""
    return await _execute_with_contract(
        ctx,
        step_name,
        fn,
        require_should_execute=require_should_execute,
        skip_reason_attr=skip_reason_attr,
    )


async def execute_pipeline_step_async(
    ctx: Any | None,
    step_name: str,
    fn: Callable[[], Awaitable[T]],
    *,
    require_should_execute: bool = True,
    skip_reason_attr: str = "tick_summarize_idle_reason",
) -> T | None:
    """Async scheduler/worker entry — alias enforcing same kernel."""
    return await _execute_with_contract(
        ctx,
        step_name,
        fn,
        require_should_execute=require_should_execute,
        skip_reason_attr=skip_reason_attr,
    )


async def _execute_with_contract(
    ctx: Any | None,
    step_name: str,
    fn: Callable[[], Awaitable[T]],
    *,
    require_should_execute: bool,
    skip_reason_attr: str,
) -> T | None:
    from app.recovery.pipeline_context_builder import build_pipeline_decision_context
    from app.state.pipeline_decision_engine import (
        apply_pipeline_decision,
        log_pipeline_decision_trace,
        make_pipeline_decision,
    )

    trace_id = uuid.uuid4().hex[:16]
    trace_tok = _trace_id.set(trace_id)
    depth_tok: Token[int] = _wrapper_depth.set(_wrapper_depth.get() + 1)
    step_tok: Token[str] = _current_step.set(step_name)
    _wrapper_entry_logged.set(False)
    _decision_engine_called.set(False)

    if ctx is not None:
        setattr(ctx, "pipeline_trace_id", trace_id)

    pctx = build_pipeline_decision_context()
    decision = make_pipeline_decision(pctx)
    _decision_engine_called.set(True)

    if ctx is not None:
        apply_pipeline_decision(ctx, source=f"wrapper:{step_name}", context=pctx)
    else:
        apply_pipeline_decision(source=f"wrapper:{step_name}", context=pctx)

    log_pipeline_decision_trace(pctx, decision, source=f"wrapper:{step_name}")
    _log_execution_trace(
        phase="wrapper_entry",
        step_name=step_name,
        decision=decision,
        trace_id=trace_id,
        use_fallback=decision.use_fallback,
    )

    fn_executed = False
    final: str | None = None
    try:
        if require_should_execute and step_name in ("summarize", "publish", "minimal_draft"):
            if not decision.should_execute:
                reason = f"wrapper_blocked:{decision.reason}"
                final = f"blocked:{reason}"
                if ctx is not None and hasattr(ctx, skip_reason_attr):
                    setattr(ctx, skip_reason_attr, reason)
                _log_execution_trace(
                    phase="wrapper_exit",
                    step_name=step_name,
                    decision=decision,
                    trace_id=trace_id,
                    final_result=final,
                )
                _validate_execution_contract(
                    step_name=step_name,
                    trace_id=trace_id,
                    final_result=final,
                    fn_executed=False,
                )
                return None
            if pctx.raw_unprocessed > 0 and not decision.summarize_enabled and step_name == "summarize":
                reason = f"backlog_but_summarize_disabled:{decision.reason}"
                final = f"fatal:{reason}"
                if ctx is not None and hasattr(ctx, skip_reason_attr):
                    setattr(ctx, skip_reason_attr, reason)
                log_event(
                    logger,
                    "PIPELINE_FATAL_BREAK",
                    reason=reason,
                    raw_unprocessed=pctx.raw_unprocessed,
                    trace_id=trace_id,
                )
                _log_execution_trace(
                    phase="wrapper_exit",
                    step_name=step_name,
                    decision=decision,
                    trace_id=trace_id,
                    final_result=final,
                )
                _validate_execution_contract(
                    step_name=step_name,
                    trace_id=trace_id,
                    final_result=final,
                    fn_executed=False,
                )
                if _bypass_strict():
                    raise RuntimeError(reason)
                return None

        result = await _run_wrapped_pipeline_coroutine(fn)
        fn_executed = True
        final = _describe_result(result, ctx=ctx, step_name=step_name)
        _log_execution_trace(
            phase="wrapper_exit",
            step_name=step_name,
            decision=decision,
            trace_id=trace_id,
            executed_function=step_name,
            final_result=final,
            use_fallback=decision.use_fallback,
        )
        _account_backlog_after_step(ctx, pctx, step_name, final)
        _validate_execution_contract(
            step_name=step_name,
            trace_id=trace_id,
            final_result=final,
            fn_executed=True,
        )
        return result
    except Exception as exc:
        final = f"error:{repr(exc)[:200]}"
        _log_execution_trace(
            phase="wrapper_exit",
            step_name=step_name,
            decision=decision,
            trace_id=trace_id,
            executed_function=step_name,
            final_result=final,
        )
        _validate_execution_contract(
            step_name=step_name,
            trace_id=trace_id,
            final_result=final,
            fn_executed=True,
        )
        raise
    finally:
        _reset_tokens(depth_tok, step_tok, trace_tok)


async def _run_wrapped_pipeline_coroutine(fn: Callable[[], Awaitable[T]]) -> T:
    """Internal coroutine runner — appears on stack as allowed frame."""
    return await fn()


def _reset_tokens(depth_tok: Token[int], step_tok: Token[str], trace_tok: Token[str]) -> None:
    _wrapper_depth.reset(depth_tok)
    _current_step.reset(step_tok)
    _trace_id.reset(trace_tok)


def _describe_result(result: Any, *, ctx: Any | None, step_name: str) -> str:
    if result is None:
        if ctx is not None and step_name in ("summarize", "minimal_draft"):
            did = getattr(ctx, "tick_draft_id", None)
            idle = getattr(ctx, "tick_summarize_idle_reason", "") or ""
            if did:
                return f"draft_created:{did}"
            if idle and idle != "none":
                return f"explicit_reject:{idle}"
            return "no_result_no_trace"
        if ctx is not None and step_name == "publish":
            po = getattr(ctx, "tick_publish_outcome", "not_reached")
            return f"publish_outcome:{po}"
        return "explicit_none"
    if isinstance(result, int):
        return f"draft_id:{result}"
    outcome = getattr(result, "outcome", None)
    if outcome is not None:
        return f"publish:{getattr(outcome, 'value', outcome)}"
    return type(result).__name__


def _account_backlog_after_step(
    ctx: Any | None,
    pctx: Any,
    step_name: str,
    final_result: str,
) -> None:
    if pctx.raw_unprocessed <= 0 or step_name not in ("summarize", "minimal_draft"):
        return
    if final_result.startswith("draft_created") or final_result.startswith("draft_id:"):
        return
    if final_result.startswith("explicit_reject") or final_result.startswith("explicit_none"):
        return
    if final_result.startswith("blocked:"):
        return
    log_event(
        logger,
        "PIPELINE_BACKLOG_CONTRACT_VIOLATION",
        step=step_name,
        raw_unprocessed=pctx.raw_unprocessed,
        final_result=final_result,
        trace_id=current_trace_id(),
        recovery="enforce_explicit_reject_or_draft",
    )
    if _bypass_strict():
        raise RuntimeError(f"backlog contract violation: {final_result}")


async def execute_pipeline_publish(
    ctx: Any | None,
    *,
    draft_id: int,
    publish_fn: Callable[[], Awaitable[T]],
) -> T | None:
    """Publish path — must use wrapper."""
    return await execute_pipeline_step(
        ctx,
        "publish",
        publish_fn,
        require_should_execute=True,
        skip_reason_attr="tick_publish_outcome",
    )


def register_async_pipeline_task(
    coro: Awaitable[T],
    *,
    name: str,
    step_name: str = "async_task",
) -> Any:
    """
    Schedule asyncio work that will run pipeline code — marks task metadata only.
    The coroutine itself must call execute_pipeline_step_async internally.
    """
    from app.runtime.task_orchestrator import create_traced_task

    trace = current_trace_id() or None
    log_event(
        logger,
        "pipeline.async_task_registered",
        task_name=name,
        step_name=step_name,
        enforcement=runtime_enforcement_mode().value,
        trace_id=trace or "",
    )
    return create_traced_task(
        name,
        coro,  # type: ignore[arg-type]
        trace_id=trace,
        owner="pipeline.wrapper",
        metadata={
            "task_type": step_name,
            **(
                {"phase": step_name}
                if step_name in ("collect", "summarize", "publish")
                else {}
            ),
        },
        name=name,
    )
