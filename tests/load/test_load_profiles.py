from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from utils.soak_simulation import PROFILE_HANDLERS, run_soak_simulation


def test_all_profiles_register() -> None:
    assert set(PROFILE_HANDLERS) == {"low", "medium", "burst", "noisy_duplicate_storm"}


def test_burst_profile_increments_counters() -> None:
    s = minimal_test_settings()
    r = asyncio.run(run_soak_simulation(s, "burst", max_ticks=5, tick_interval_sec=0.0))
    posts = r.snapshots[-1].counters.get("posts_collected", 0)
    assert int(posts) >= 12 * 5
