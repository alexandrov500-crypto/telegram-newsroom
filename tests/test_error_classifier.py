from __future__ import annotations

import asyncio
import sys

import pytest

from utils.error_classifier import ClassifiedError, classify_runtime_error


def test_value_error_validation():
    c = classify_runtime_error(ValueError("bad input"))
    assert c.category == "validation"
    assert c.retryable is False


def test_runtime_error_startup_message():
    c = classify_runtime_error(RuntimeError("Startup validation failed: x"))
    assert c.category == "validation"


def test_connection_error_network():
    c = classify_runtime_error(ConnectionError("reset"))
    assert c.category == "network"
    assert c.retryable is True


def test_asyncio_timeout_scheduler():
    c = classify_runtime_error(asyncio.TimeoutError())
    assert c.category == "scheduler"
    assert c.retryable is True


def test_cancelled_scheduler():
    c = classify_runtime_error(asyncio.CancelledError())
    assert c.category == "scheduler"
    assert c.retryable is False


def test_unknown_fallback():
    c = classify_runtime_error(KeyError("missing"))
    assert c.category == "unknown"
    assert isinstance(c, ClassifiedError)


def test_nested_cause_sqlalchemy():
    try:
        import sqlalchemy.exc as sa_exc

        inner = sa_exc.OperationalError("stmt", {}, Exception("e"))
        raise RuntimeError("outer") from inner
    except RuntimeError as exc:
        c = classify_runtime_error(exc)
    assert c.category == "database"


@pytest.mark.skipif(sys.version_info < (3, 11), reason="ExceptionGroup requires 3.11+")
def test_exception_group_picks_first_meaningful():
    def boom() -> None:
        raise ExceptionGroup("eg", [ValueError("inner val")])

    exc: BaseException | None = None
    try:
        boom()
    except BaseException as e:
        exc = e
    assert exc is not None
    c = classify_runtime_error(exc)
    assert c.category == "validation"
