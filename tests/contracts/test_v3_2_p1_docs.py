"""v3.2 P1 operational tooling documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

P1_DOCS = (
    "docs/architecture/ADR-030-v3-2-operational-tooling-scope.md",
    "docs/operations/queue_introspection.md",
    "docs/operations/publish_timeline_reporting.md",
    "docs/runbooks/operator_shift_checklist.md",
    "docs/releases/v3_2_p1_exit_criteria.md",
)

P1_TOOLS = (
    "tools/ops_metrics_snapshot.py",
    "tools/queue_introspection.py",
    "tools/publish_timeline_report.py",
)


@pytest.mark.parametrize("rel", P1_DOCS + P1_TOOLS)
def test_v3_2_p1_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel
