"""Backoff, jitter, deadlines, and error classification for worker jobs."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

from workers.types import ErrorClass, StructuredJobError

logger = logging.getLogger(__name__)


def classify_exception(exc: BaseException) -> ErrorClass:
    if isinstance(exc, StructuredJobError):
        return exc.classification
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ErrorClass.TRANSIENT
    msg = str(exc).lower()
    if "429" in msg or "rate" in msg or "flood" in msg:
        return ErrorClass.RATE_LIMITED
    if "401" in msg or "403" in msg or "permission" in msg:
        return ErrorClass.PERMANENT
    if "openai" in msg or "telegram" in msg or "connection" in msg or "temporar" in msg:
        return ErrorClass.EXTERNAL_SERVICE_FAILURE
    return ErrorClass.TRANSIENT


def permanent_never_retries(cls: ErrorClass) -> bool:
    return cls == ErrorClass.PERMANENT


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    base_backoff_sec: float
    jitter_ratio: float
    retry_deadline_monotonic: float

    def next_delay_sec(self, attempt: int) -> float:
        base = min(300.0, self.base_backoff_sec * (2 ** max(0, attempt)))
        jitter = base * self.jitter_ratio * random.random()
        return max(0.05, base + jitter)

    def exhausted(self, attempt: int) -> bool:
        return attempt >= self.max_attempts

    def past_deadline(self) -> bool:
        return time.monotonic() >= self.retry_deadline_monotonic


def build_policy_from_settings(settings: Any, *, envelope_attempt: int) -> RetryPolicy:
    max_a = max(1, int(getattr(settings, "openai_json_max_retries", 3)) + 2)
    base = 0.75
    jitter = float(getattr(settings, "worker_retry_jitter_ratio", 0.12) or 0.12)
    deadline = time.monotonic() + float(getattr(settings, "worker_retry_deadline_sec", 3600.0) or 3600.0)
    return RetryPolicy(
        max_attempts=max_a,
        base_backoff_sec=base,
        jitter_ratio=jitter,
        retry_deadline_monotonic=deadline,
    )
