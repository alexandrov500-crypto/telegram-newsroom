"""v1.1 chaos validation documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

RUNBOOKS = (
    "docs/runbooks/REDIS_DOWN.md",
    "docs/runbooks/SQLITE_LOCKED.md",
    "docs/runbooks/PARTIAL_PUBLISH.md",
    "docs/runbooks/FAILED_RESTORE.md",
    "docs/runbooks/TELETHON_SESSION_LOST.md",
    "docs/runbooks/RETRY_STORM.md",
    "docs/runbooks/DEGRADED_MODE.md",
)

RUNBOOK_SECTIONS = (
    "## Symptoms",
    "## Detection",
    "## Immediate Mitigation",
    "## Safe Recovery",
    "## Validation Steps",
    "## Rollback Strategy",
    "## Evidence Collection",
    "## Escalation Notes",
)


@pytest.mark.parametrize("rel", RUNBOOKS)
def test_runbook_exists(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", RUNBOOKS)
def test_runbook_sections(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    for section in RUNBOOK_SECTIONS:
        assert section in text, f"{rel} missing {section}"


def test_v1_1_validation_report_exists() -> None:
    assert (REPO / "docs/v1_1_operational_validation_report.md").is_file()


def test_chaos_test_directory_exists() -> None:
    assert (REPO / "tests/chaos/framework.py").is_file()


def test_validation_report_no_mandatory_contract_break() -> None:
    text = (REPO / "docs/v1_1_operational_validation_report.md").read_text(encoding="utf-8").lower()
    assert "no frozen contract" in text or "no frozen contract changes" in text
    assert "opt-in" in text


def test_makefile_chaos_target() -> None:
    text = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "chaos-test" in text
