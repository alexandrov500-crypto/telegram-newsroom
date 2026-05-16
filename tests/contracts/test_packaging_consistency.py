"""Packaging and v1.0.0 release identity consistency (contracts)."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

EXPECTED_VERSION = "1.0.0"
EXPECTED_RELEASE_STATUS = "stable"

REQUIRED_DOCS = (
    "docs/START_HERE.md",
    "docs/STABILITY_GUARANTEES.md",
    "docs/MAINTENANCE_POLICY.md",
    "docs/RELEASE_FINALIZATION.md",
    "docs/REPRODUCIBILITY.md",
    "CHANGELOG.md",
    "LICENSE",
    "SECURITY.md",
    "SUPPORT.md",
)

DEPLOY_ASSETS = (
    "deploy/example.env.production-lite",
    "deploy/docker-compose.production-lite.yml",
    "deploy/systemd/newsroom-nightly.service",
)

EXAMPLE_ASSETS = (
    "examples/runtime_samples/runtime_index.json",
    "examples/demo_walkthrough/01_nightly_run.sh",
    "examples/demo_outputs/runtime-index.txt",
)

REQUIRED_CONSOLE_SCRIPTS = (
    "newsroom-health",
    "newsroom-runtime-index",
    "newsroom-verify-runtime",
)

REQUIRED_MAKE_TARGETS = (
    "release-check",
    "runtime-help",
    "docs-map",
    "quality",
    "contracts",
    "smoke",
)


def test_version_ssot_newsroom() -> None:
    from newsroom._version import RELEASE_STATUS, VERSION

    assert VERSION == EXPECTED_VERSION
    assert RELEASE_STATUS == EXPECTED_RELEASE_STATUS
    import newsroom

    assert newsroom.__version__ == EXPECTED_VERSION
    assert newsroom.__release_status__ == EXPECTED_RELEASE_STATUS


def test_version_app_versioning_reexport() -> None:
    from app.versioning import APP_VERSION

    assert APP_VERSION == EXPECTED_VERSION


def test_pyproject_dynamic_version_config() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dynamic"] == ["version"]
    raw = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'attr = "newsroom.__version__"' in raw
    assert "MIT" in raw


def test_changelog_documents_v1() -> None:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [1.0.0]" in text
    assert "frozen" in text.lower()


@pytest.mark.parametrize("rel", REQUIRED_DOCS)
def test_required_release_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", DEPLOY_ASSETS)
def test_deploy_assets_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", EXAMPLE_ASSETS)
def test_example_assets_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_manifest_includes_docs_and_examples() -> None:
    text = (REPO / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include docs" in text
    assert "recursive-include examples" in text
    assert "include LICENSE" in text


def test_pyproject_entry_points_declared() -> None:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    for name in REQUIRED_CONSOLE_SCRIPTS:
        assert name in scripts, name


def test_makefile_required_targets() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in REQUIRED_MAKE_TARGETS:
        assert re.search(rf"^{re.escape(target)}:", makefile, re.MULTILINE), target


def test_runtime_help_target_runs() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "runtime-help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Inspect / catalog:" in proc.stdout


def test_docs_map_target_runs() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "docs-map"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "START_HERE" in proc.stdout
