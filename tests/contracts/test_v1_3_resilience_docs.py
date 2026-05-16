"""v1.3 resilience documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

V13_RUNBOOKS = (
    "docs/runbooks/SQLITE_LONG_RUNNING_MAINTENANCE.md",
    "docs/runbooks/RETRY_STORM_RECOVERY.md",
    "docs/runbooks/WAL_GROWTH.md",
    "docs/runbooks/EVIDENCE_RETENTION.md",
    "docs/runbooks/LONG_RUNNING_NODE_MAINTENANCE.md",
    "docs/runbooks/MEMORY_GROWTH_INVESTIGATION.md",
    "docs/runbooks/REDIS_RECONNECT_STORM.md",
)

SECTION_MARKERS = ("## Detection", "## Mitigation", "## Validation")


@pytest.mark.parametrize("rel", V13_RUNBOOKS)
def test_v13_runbooks_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", V13_RUNBOOKS)
def test_v13_runbook_has_core_sections(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    for marker in SECTION_MARKERS:
        assert marker in text, f"{rel} missing {marker}"


def test_operational_envelope_exists() -> None:
    assert (REPO / "docs/v1_3_operational_envelope.md").is_file()


def test_resilience_report_exists() -> None:
    text = (REPO / "docs/v1_3_resilience_validation_report.md").read_text(encoding="utf-8")
    assert "Soak test summary" in text
    assert "opt-in" in text.lower()


def test_runtime_drift_monitor_module() -> None:
    assert (REPO / "utils/runtime_drift_monitor.py").is_file()


def test_soak_harness_module() -> None:
    assert (REPO / "tests/soak/harness.py").is_file()


def test_makefile_resilience_targets() -> None:
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "soak-test" in mk
    assert "resilience-validate" in mk
