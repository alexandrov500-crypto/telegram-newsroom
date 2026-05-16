"""Operational reality-check documentation and wording contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_real_world_validation_doc_exists() -> None:
    text = (REPO / "docs/REAL_WORLD_VALIDATION.md").read_text(encoding="utf-8")
    assert "Validated workflows" in text
    assert "release-qualify" in text
    assert "runtime_samples" in text


def test_operational_confidence_doc_exists() -> None:
    text = (REPO / "docs/OPERATIONAL_CONFIDENCE.md").read_text(encoding="utf-8")
    assert "Installation confidence" in text
    assert "release-qualify" in text
    assert "make release-check" in text


def test_no_stale_primary_rc1_wording_in_operator_docs() -> None:
    """rc1 may appear in CHANGELOG history; operator-facing docs should say 1.0.0 stable."""
    for rel in (
        "docs/START_HERE.md",
        "docs/OPERATOR_QUICKSTART.md",
        "docs/RELEASE_FINALIZATION.md",
        "README.md",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "1.0.0-rc1" not in text, rel
        assert "1.0.0" in text or "v1.0.0" in text or "stable" in text.lower()


def test_release_check_vs_release_qualify_docs() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "release-check:" in makefile
    assert "release-qualify:" in makefile
    rf = (REPO / "docs/RELEASE_FINALIZATION.md").read_text(encoding="utf-8")
    assert "make release-check" in rf
    assert "make release-qualify" in rf
    assert "RUNTIME_BUNDLE" in rf


def test_runtime_samples_readme_warns_verify() -> None:
    text = (REPO / "examples/runtime_samples/README.md").read_text(encoding="utf-8")
    assert "verify-runtime" in text
    assert "placeholder" in text.lower() or "Do not" in text


def test_operator_quickstart_uses_current_make_targets() -> None:
    text = (REPO / "docs/OPERATOR_QUICKSTART.md").read_text(encoding="utf-8")
    assert "make runtime-index" in text
    assert "make runtime-nightly" in text
    assert "make runtime-help" in text
    assert "release-check RUNTIME_BUNDLE" not in text


def test_index_summary_includes_operator_actions_on_fail() -> None:
    from observability.runtime_index import build_runtime_index, render_index_summary

    index = build_runtime_index(REPO / "nonexistent-output-dir-for-test")
    summary = render_index_summary(index)
    assert index["index_status"] == "FAIL"
    assert "Operator actions:" in summary
    assert "runtime-nightly" in summary


def test_verify_summary_includes_samples_warning() -> None:
    from observability.runtime_verify import render_verify_summary

    summary = render_verify_summary({"verification_status": "FAIL"})
    assert "Operator actions:" in summary
    assert "runtime_samples" in summary


def test_make_help_documents_release_check() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "release-check" in proc.stdout


def test_terminology_frozen_governance_in_start_here() -> None:
    text = (REPO / "docs/START_HERE.md").read_text(encoding="utf-8")
    assert "operationally frozen" in text
    assert "production-lite" in text.lower() or "Production-lite" in text
