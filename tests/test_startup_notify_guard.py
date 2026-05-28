from __future__ import annotations

from pathlib import Path

import pytest

from app.ops.runtime.startup_notify_guard import (
    release_startup_notification_lock,
    reset_startup_notification_lock_for_tests,
    try_acquire_startup_notification_lock,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_startup_notification_lock_for_tests()
    yield
    reset_startup_notification_lock_for_tests()


def test_only_one_process_holds_notify_lock(tmp_path: Path):
    rd = str(tmp_path / "runtime")
    assert try_acquire_startup_notification_lock(rd)
    assert not try_acquire_startup_notification_lock(rd)
    release_startup_notification_lock()
    assert try_acquire_startup_notification_lock(rd)
    release_startup_notification_lock()
