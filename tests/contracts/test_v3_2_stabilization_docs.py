"""v3.2 stabilization and planning documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

OPS_DOCS = (
    "docs/operations/72h_operational_findings.md",
    "docs/operations/production_baselines.md",
    "docs/operations/postmortem_template.md",
)

ARCH_DOCS = (
    "docs/architecture/v3_2_discovery.md",
    "docs/architecture/technical_debt_registry.md",
)

GOV_DOCS = (
    "docs/governance/production_governance_audit.md",
    "docs/governance/stabilization_freeze_policy.md",
)

RELEASE_DOCS = ("docs/releases/v3_2_planning_gate.md",)


@pytest.mark.parametrize("rel", OPS_DOCS + ARCH_DOCS + GOV_DOCS + RELEASE_DOCS)
def test_v3_2_stabilization_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_freeze_policy_prohibits_retry_redesign() -> None:
    text = (REPO / "docs/governance/stabilization_freeze_policy.md").read_text(encoding="utf-8")
    assert "Retry redesign" in text or "retry redesign" in text.lower()


def test_postmortem_blameless() -> None:
    text = (REPO / "docs/operations/postmortem_template.md").read_text(encoding="utf-8")
    assert "blame" in text.lower()
    assert "blame-oriented" in text.lower()


def test_v3_2_discovery_has_not_planned_section() -> None:
    text = (REPO / "docs/architecture/v3_2_discovery.md").read_text(encoding="utf-8")
    assert "NOT planned" in text or "Out of scope" in text
