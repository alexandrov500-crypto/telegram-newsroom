"""Reusable pytest fixtures (sync) for isolated runtime paths."""

from __future__ import annotations

import pytest


@pytest.fixture
def ephemeral_newsroom_settings(tmp_path):
    """Per-test isolated SQLite file, runtime dir, and queue prefix."""
    from tests.conftest import minimal_test_settings
    from tests.helpers.runtime_factory import build_ephemeral_settings

    return build_ephemeral_settings(minimal_test_settings(), tmp_path)
