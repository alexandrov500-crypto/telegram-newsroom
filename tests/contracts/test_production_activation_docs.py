"""Production activation and release documentation contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PRODUCTION_OPS_DOCS = (
    "docs/operations/production_bootstrap.md",
    "docs/operations/production_safeguards.md",
    "docs/operations/alerting_baseline.md",
    "docs/operations/72h_stability_window.md",
)

RUNBOOKS = (
    "docs/runbooks/controlled_activation.md",
    "docs/runbooks/incident_response.md",
)

RELEASE_DOCS = (
    "docs/releases/merge_summary_v3.1.md",
    "docs/releases/release_integrity_checklist.md",
    "docs/releases/deployment_checksum_notes.md",
    "docs/releases/production_activation_signoff.md",
)


@pytest.mark.parametrize("rel", PRODUCTION_OPS_DOCS + RUNBOOKS + RELEASE_DOCS)
def test_production_activation_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_controlled_activation_has_rollback_section() -> None:
    text = (REPO / "docs/runbooks/controlled_activation.md").read_text(encoding="utf-8")
    assert "Emergency rollback" in text
    assert "DRY_RUN=true" in text


def test_production_safeguards_covers_duplicate_prevention() -> None:
    text = (REPO / "docs/operations/production_safeguards.md").read_text(encoding="utf-8")
    assert "Duplicate publish" in text
