"""v2 transition strategy documentation and guardrails contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

STRATEGY_DOCS = (
    "docs/architecture/architectural_preservation.md",
    "docs/architecture/v2_transition_strategy.md",
    "docs/architecture/technical_debt_governance.md",
    "docs/architecture/complexity_budget.md",
    "docs/architecture/evolution_decision_matrix.md",
    "docs/architecture/future_scalability_realities.md",
    "docs/architecture/maintainer_longevity.md",
    "docs/architecture/operational_philosophy.md",
    "docs/v2_transition_strategy_report.md",
)

PRESERVATION_MARKERS = (
    "## Core architectural invariants",
    "## Do not rewrite policy",
    "## Anti-platform-creep rules",
)

V2_STRATEGY_MARKERS = (
    "## What justifies v2",
    "## What does NOT justify v2",
    "## Major-version gates",
)


@pytest.mark.parametrize("rel", STRATEGY_DOCS)
def test_strategy_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_preservation_sections() -> None:
    text = (REPO / "docs/architecture/architectural_preservation.md").read_text(encoding="utf-8")
    for m in PRESERVATION_MARKERS:
        assert m in text


def test_v2_strategy_sections() -> None:
    text = (REPO / "docs/architecture/v2_transition_strategy.md").read_text(encoding="utf-8")
    for m in V2_STRATEGY_MARKERS:
        assert m in text


def test_architecture_guardrails_tool() -> None:
    assert (REPO / "tools/architecture_guardrails.py").is_file()
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/architecture_guardrails.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data.get("read_only") is True
    assert data.get("advisory_only") is True
    assert data.get("status") in ("OK", "WARNING")


def test_guardrails_no_hidden_v2_code() -> None:
    """Strategy phase must not add v2 package or alternate app entry."""
    assert not (REPO / "v2").is_dir()
    assert not (REPO / "app/v2").is_dir()
