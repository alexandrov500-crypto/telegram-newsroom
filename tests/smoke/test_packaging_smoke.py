"""Lightweight packaging / CLI smoke checks (no network, no Redis)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_pyproject_toml_parses() -> None:
    raw = (REPO / "pyproject.toml").read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    assert data["project"]["name"] == "telegram-newsroom"
    assert "dependencies" in data["project"]
    assert "pytest" in str(data["project"]["optional-dependencies"]["dev"])


def test_makefile_help_prints() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "runtime-nightly" in proc.stdout


def test_runtime_ops_cli_help() -> None:
    spec = importlib.util.spec_from_file_location("runtime_ops_cli", REPO / "tools" / "runtime_ops.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pytest.raises(SystemExit) as excinfo:
        mod.main(["--help"])
    assert excinfo.value.code == 0


def test_release_qualification_cli_help(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = importlib.util.spec_from_file_location("release_qual_cli", REPO / "tools" / "release_qualification.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", ["release_qualification.py", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        mod.main()
    assert excinfo.value.code == 0


@pytest.mark.skipif(sys.platform.startswith("win"), reason="make on Windows optional")
def test_make_dry_run_preflight() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "-n", "runtime-preflight"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "runtime_preflight.py" in proc.stdout


def test_github_workflow_files_have_expected_keys() -> None:
    wf = REPO / ".github" / "workflows"
    for name in ("tests.yml", "nightly-runtime.yml", "release-check.yml"):
        text = (wf / name).read_text(encoding="utf-8")
        assert "runs-on:" in text
        assert "python-version:" in text
        assert "actions/checkout@v4" in text


def test_shell_scripts_are_executable() -> None:
    for rel in ("scripts/nightly_runtime.sh", "scripts/release_check.sh"):
        path = REPO / rel
        assert path.is_file()
        assert os.access(path, os.X_OK), f"chmod +x {rel}"
