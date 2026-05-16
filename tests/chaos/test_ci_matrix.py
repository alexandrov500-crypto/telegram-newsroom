"""CI reliability matrix dimensions (parametrized, deterministic)."""

from __future__ import annotations

import pytest

from tests.conftest import minimal_test_settings


@pytest.mark.parametrize(
    "redis_enabled,strict,safe_retry",
    [
        (False, False, False),
        (False, False, True),
        (True, True, True),
        (True, False, False),
    ],
)
def test_settings_matrix_combinations(redis_enabled: bool, strict: bool, safe_retry: bool) -> None:
    s = minimal_test_settings(
        redis_enabled=redis_enabled,
        publish_lock_strict=strict,
        worker_retry_safe=safe_retry,
    )
    assert s.publish_lock_strict is strict
    assert s.worker_retry_safe is safe_retry
