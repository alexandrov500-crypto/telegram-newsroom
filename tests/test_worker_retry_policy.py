from __future__ import annotations

from workers.retry import build_policy_from_settings, classify_exception, permanent_never_retries
from workers.types import ErrorClass, StructuredJobError


def test_retry_policy_delay_positive() -> None:
    class _S:
        openai_json_max_retries = 3
        worker_retry_jitter_ratio = 0.1
        worker_retry_deadline_sec = 3600.0

    p = build_policy_from_settings(_S(), envelope_attempt=0)
    d = p.next_delay_sec(0)
    assert d >= 0.05


def test_classify_structured_permanent() -> None:
    e = StructuredJobError("x", classification=ErrorClass.PERMANENT)
    assert classify_exception(e) == ErrorClass.PERMANENT
    assert permanent_never_retries(ErrorClass.PERMANENT) is True
