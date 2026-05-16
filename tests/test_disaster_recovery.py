from __future__ import annotations

import pytest

from app.startup_validation import validate_settings_for_launch
from tests.conftest import minimal_test_settings


def test_production_rejects_memory_sqlite() -> None:
    s = minimal_test_settings(
        deployment_profile="production",
        database_url="sqlite+aiosqlite:///:memory:",
        dry_run=False,
    )
    with pytest.raises(RuntimeError, match=":memory:"):
        validate_settings_for_launch(s)


def test_production_rejects_dry_run_without_override(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ALLOW_PRODUCTION_DRY_RUN", raising=False)
    dbf = tmp_path / "dr.sqlite"
    s = minimal_test_settings(
        deployment_profile="production",
        dry_run=True,
        database_url=f"sqlite+aiosqlite:///{dbf}",
    )
    with pytest.raises(RuntimeError, match="DRY_RUN"):
        validate_settings_for_launch(s)


def test_corrupted_zip_validate_fails(tmp_path) -> None:
    p = tmp_path / "bad.zip"
    p.write_bytes(b"not a zip")
    import subprocess
    import sys
    from pathlib import Path

    cli = Path(__file__).resolve().parents[1] / "tools" / "backup_cli.py"
    proc = subprocess.run(
        [sys.executable, str(cli), "backup-validate", str(p)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
