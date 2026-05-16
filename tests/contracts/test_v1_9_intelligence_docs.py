"""v1.9 operational intelligence contracts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

INTELLIGENCE_DOCS = (
    "docs/operational_intelligence.md",
    "docs/v1_9_operational_intelligence_report.md",
)

INTELLIGENCE_TOOLS = (
    "tools/maintenance_forecast.py",
    "tools/drift_forecast.py",
    "tools/maintenance_recommendations.py",
    "tools/ops_summary.py",
)

INTELLIGENCE_UTILS = (
    "utils/operational_trends.py",
    "utils/recovery_intelligence.py",
    "utils/operational_health.py",
)

DOC_SECTIONS = (
    "# Predictive Maintenance Philosophy",
    "# Advisory vs Mandatory Actions",
    "# Risk Scoring Rules",
    "# Forecast Confidence Limits",
    "# Unsupported Prediction Claims",
    "# Operator Responsibility Boundaries",
)


@pytest.mark.parametrize("rel", INTELLIGENCE_DOCS + INTELLIGENCE_TOOLS + INTELLIGENCE_UTILS)
def test_intelligence_artifacts_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_operational_intelligence_sections() -> None:
    text = (REPO / "docs/operational_intelligence.md").read_text(encoding="utf-8")
    for marker in DOC_SECTIONS:
        assert marker in text


def test_ops_summary_runs() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/ops_summary.py"), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
