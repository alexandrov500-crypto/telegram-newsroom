"""OpenAI circuit breaker: fail-open runtime, temporary OPENAI_DISABLED after bursts."""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from enum import Enum
from typing import Any

from app.runtime_lifecycle import emit_lifecycle
from app.runtime_metrics import inc_openai_failure_total
from utils.metrics import inc, set_gauge
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

OPENAI_CIRCUIT_OPEN = "openai_circuit_open"
OPENAI_RECOVERY_ATTEMPTS = "openai_recovery_attempts_total"


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class OpenAICircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        open_sec: float = 300.0,
        recovery_probe_sec: float = 60.0,
        base_backoff_sec: float = 1.0,
        max_backoff_sec: float = 30.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._open_sec = open_sec
        self._recovery_probe_sec = recovery_probe_sec
        self._base_backoff_sec = base_backoff_sec
        self._max_backoff_sec = max_backoff_sec
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._open_until_mono = 0.0
        self._last_failure_reason = ""

    def reset_for_tests(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._open_until_mono = 0.0
            self._last_failure_reason = ""
        set_gauge(OPENAI_CIRCUIT_OPEN, 0.0)

    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_advance_half_open()
            return self._state

    def is_openai_disabled(self) -> bool:
        return self.state() != CircuitState.CLOSED

    def allow_request(self) -> bool:
        with self._lock:
            self._maybe_advance_half_open()
            return self._state != CircuitState.OPEN

    def _maybe_advance_half_open(self) -> None:
        now = time.monotonic()
        if self._state == CircuitState.OPEN and now >= self._open_until_mono:
            prev = self._state.value
            self._state = CircuitState.HALF_OPEN
            inc(OPENAI_RECOVERY_ATTEMPTS)
            set_gauge(OPENAI_CIRCUIT_OPEN, 0.5)
            log_event(
                logger,
                "openai.circuit.half_open",
                recovery_probe_sec=self._recovery_probe_sec,
                subsystem="openai",
            )
            emit_lifecycle("runtime.recovery.probe", circuit_state="half_open")
            self._telemetry_state(prev, "half_open")

    def record_success(self) -> None:
        with self._lock:
            prev = self._state
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._open_until_mono = 0.0
            self._last_failure_reason = ""
        set_gauge(OPENAI_CIRCUIT_OPEN, 0.0)
        if prev != CircuitState.CLOSED:
            self._telemetry_state(prev.value, "closed")
            emit_lifecycle("runtime.recovered.full", circuit_state="closed")
            log_event(logger, "openai.circuit.closed", subsystem="openai")
            try:
                from app.runtime_activity import record_fallback_success

                record_fallback_success()
                from app.state.pipeline_decision_engine import apply_pipeline_decision
                from app.state.pipeline_execution_wrapper import pipeline_evaluation_only

                with pipeline_evaluation_only():
                    apply_pipeline_decision(source="circuit_record_success")
            except Exception:
                pass

    def record_failure(self, reason: str = "") -> None:
        inc_openai_failure_total()
        reason_s = (reason or "unknown")[:300]
        opened = False
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_reason = reason_s
            if self._state == CircuitState.HALF_OPEN:
                self._open_circuit_locked(reason_s)
                opened = True
            elif (
                self._state == CircuitState.CLOSED
                and self._consecutive_failures >= self._failure_threshold
            ):
                self._open_circuit_locked(reason_s)
                opened = True
        if opened:
            emit_lifecycle(
                "runtime.degraded",
                reason="openai_circuit_open",
                openai_circuit_state="open",
                failure_count=self._consecutive_failures,
            )
            self._sync_ai_pipeline_flag(disabled=True)

    def force_open(self, reason: str, *, duration_sec: float | None = None) -> None:
        """Startup / region-block path: disable OpenAI without crashing."""
        with self._lock:
            self._open_circuit_locked(reason[:300], duration_sec=duration_sec)
        emit_lifecycle(
            "runtime.degraded",
            reason=reason[:200],
            openai_circuit_state="open",
        )
        self._sync_ai_pipeline_flag(disabled=True)

    def _open_circuit_locked(self, reason: str, *, duration_sec: float | None = None) -> None:
        dur = duration_sec if duration_sec is not None else self._open_sec
        prev = self._state.value
        self._state = CircuitState.OPEN
        self._open_until_mono = time.monotonic() + max(self._recovery_probe_sec, dur)
        set_gauge(OPENAI_CIRCUIT_OPEN, 1.0)
        self._telemetry_state(prev, "open")
        log_event(
            logger,
            "openai.circuit.open",
            reason=reason,
            open_sec=round(dur, 1),
            consecutive_failures=self._consecutive_failures,
            recovery="OPENAI_DISABLED",
            subsystem="openai",
        )

    @staticmethod
    def _telemetry_state(prev: str, new: str) -> None:
        try:
            from ops.recovery_telemetry import note_circuit_state, note_degradation_started, note_full_recovery

            note_circuit_state(prev, new)
            if new == "open":
                note_degradation_started()
            if new == "closed" and prev in {"open", "half_open"}:
                note_full_recovery()
        except Exception:
            pass

    def backoff_delay_sec(self, attempt: int) -> float:
        """Exponential backoff with jitter (attempt is 1-based)."""
        exp = min(self._max_backoff_sec, self._base_backoff_sec * (2 ** max(0, attempt - 1)))
        jitter = random.uniform(0.0, min(1.0, exp * 0.25))
        return min(self._max_backoff_sec, exp + jitter)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._maybe_advance_half_open()
            return {
                "state": self._state.value,
                "openai_disabled": self._state != CircuitState.CLOSED,
                "consecutive_failures": self._consecutive_failures,
                "open_until_mono": self._open_until_mono if self._state == CircuitState.OPEN else None,
                "last_failure_reason": self._last_failure_reason[:120] if self._last_failure_reason else "",
            }

    @staticmethod
    def _sync_ai_pipeline_flag(*, disabled: bool) -> None:
        try:
            from app.state.pipeline_decision_engine import apply_pipeline_decision
            from app.state.pipeline_execution_wrapper import pipeline_evaluation_only

            with pipeline_evaluation_only():
                apply_pipeline_decision(source="openai_circuit_sync")
        except Exception:
            pass


_CIRCUIT: OpenAICircuitBreaker | None = None


def get_openai_circuit() -> OpenAICircuitBreaker:
    global _CIRCUIT
    if _CIRCUIT is None:
        _CIRCUIT = OpenAICircuitBreaker(
            failure_threshold=_env_int("OPENAI_CIRCUIT_FAILURE_THRESHOLD", 5),
            open_sec=_env_float("OPENAI_CIRCUIT_OPEN_SEC", 300.0),
            recovery_probe_sec=_env_float("OPENAI_CIRCUIT_RECOVERY_PROBE_SEC", 60.0),
            base_backoff_sec=_env_float("OPENAI_CIRCUIT_BASE_BACKOFF_SEC", 1.0),
            max_backoff_sec=_env_float("OPENAI_CIRCUIT_MAX_BACKOFF_SEC", 30.0),
        )
    return _CIRCUIT


def reset_openai_circuit_for_tests() -> None:
    global _CIRCUIT
    if _CIRCUIT is not None:
        _CIRCUIT.reset_for_tests()
    _CIRCUIT = None
