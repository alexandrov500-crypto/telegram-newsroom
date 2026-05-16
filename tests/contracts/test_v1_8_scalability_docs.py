"""v1.8 scalability documentation and tooling contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SCALABILITY_DOCS = (
    "docs/scalability/operational_topologies.md",
    "docs/scalability/capacity_planning.md",
    "docs/scalability/postgresql_evolution_path.md",
    "docs/scalability/multi_worker_discipline.md",
    "docs/scalability/unsupported_deployments.md",
    "docs/scalability/scaling_governance.md",
    "docs/v1_8_scalability_boundaries_report.md",
)

SCALING_RUNBOOKS = (
    "docs/runbooks/scaling/QUEUE_PRESSURE.md",
    "docs/runbooks/scaling/WAL_PRESSURE.md",
    "docs/runbooks/scaling/RETRY_SATURATION.md",
    "docs/runbooks/scaling/REDIS_RECONNECT_PRESSURE.md",
    "docs/runbooks/scaling/SNAPSHOT_SIZE_GROWTH.md",
    "docs/runbooks/scaling/MULTI_WORKER_CONTENTION.md",
    "docs/runbooks/scaling/SCHEDULER_SATURATION.md",
)

RUNBOOK_MARKERS = (
    "## Detection",
    "## Mitigation",
    "## Safe scaling guidance",
    "## Rollback",
    "## Evidence collection",
    "## Escalation thresholds",
)


@pytest.mark.parametrize("rel", SCALABILITY_DOCS)
def test_scalability_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", SCALING_RUNBOOKS)
def test_scaling_runbooks_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", SCALING_RUNBOOKS)
def test_scaling_runbook_sections(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    for marker in RUNBOOK_MARKERS:
        assert marker in text, f"{rel} missing {marker}"


def test_scalability_diagnostics_tool() -> None:
    assert (REPO / "tools/scalability_diagnostics.py").is_file()
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/scalability_diagnostics.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data.get("read_only") is True
    assert data.get("schema_version") == 1


def test_topology_doc_lists_t0_t4() -> None:
    text = (REPO / "docs/scalability/operational_topologies.md").read_text(encoding="utf-8")
    for tag in ("T0", "T1", "T2", "T3", "T4"):
        assert tag in text
