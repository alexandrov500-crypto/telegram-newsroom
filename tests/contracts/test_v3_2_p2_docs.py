"""v3.2 P2 documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DOCS = (
    "docs/architecture/ADR-031-operational-analytics-layer.md",
    "docs/operations/metrics_retention_policy.md",
    "docs/releases/v3_2_p2_exit_criteria.md",
)

TOOLS = (
    "tools/ops_analytics_aggregate.py",
    "tools/ops_visualize.py",
    "tools/ops_archive.py",
    "tools/generate_shift_handoff.py",
)


@pytest.mark.parametrize("rel", DOCS + TOOLS)
def test_p2_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel
