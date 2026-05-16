"""v1.6 security documentation and tooling contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SECURITY_DOCS = (
    "docs/security/secrets_hygiene.md",
    "docs/security/supply_chain_integrity.md",
    "docs/security/artifact_integrity.md",
    "docs/security/auditability.md",
    "docs/security/trust_boundaries.md",
    "docs/v1_6_security_hardening_report.md",
)

SECURITY_RUNBOOKS = (
    "docs/runbooks/security/TOKEN_ROTATION.md",
    "docs/runbooks/security/REDACTION_FAILURE.md",
    "docs/runbooks/security/SUSPECTED_SECRET_LEAK.md",
    "docs/runbooks/security/COMPROMISED_RUNTIME.md",
    "docs/runbooks/security/EVIDENCE_TAMPERING.md",
    "docs/runbooks/security/UNSAFE_CONFIGURATION.md",
    "docs/runbooks/security/INCIDENT_CONTAINMENT.md",
)

RUNBOOK_MARKERS = ("## Detection", "## Containment", "## Recovery")


@pytest.mark.parametrize("rel", SECURITY_DOCS)
def test_security_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", SECURITY_RUNBOOKS)
def test_security_runbooks_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", SECURITY_RUNBOOKS)
def test_security_runbook_sections(rel: str) -> None:
    text = (REPO / rel).read_text(encoding="utf-8")
    for marker in RUNBOOK_MARKERS:
        assert marker in text, f"{rel} missing {marker}"


def test_security_redaction_module() -> None:
    assert (REPO / "utils/security_redaction.py").is_file()


def test_security_readiness_default() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/security_readiness.py"), "--skip-tools"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["status"] == "OK"


def test_makefile_security_validate() -> None:
    assert "security-validate" in (REPO / "Makefile").read_text(encoding="utf-8")
