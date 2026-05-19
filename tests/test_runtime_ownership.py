from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bot.runtime.instance import create_runtime_identity, generate_runtime_instance_id
from bot.runtime.ownership import RuntimeOwnershipLock, read_lock_holder


def test_generate_runtime_instance_id_contains_profile() -> None:
    iid = generate_runtime_instance_id("minimal_pilot")
    assert "minimalpilot" in iid.replace("_", "")
    assert str(os.getpid()) in iid


def test_lock_holder_written(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("fcntl lock not on Windows")
    lock_path = tmp_path / "operator-runtime.lock"
    ident = create_runtime_identity("minimal_pilot")
    lock = RuntimeOwnershipLock(lock_path)
    lock.acquire(ident)
    holder = read_lock_holder(lock_path)
    assert holder["runtime_instance_id"] == ident.runtime_instance_id
    assert holder["pid"] == os.getpid()
    lock.release()
