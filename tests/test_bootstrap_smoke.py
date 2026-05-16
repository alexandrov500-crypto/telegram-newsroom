from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_bootstrap_script_exits_zero() -> None:
    r = subprocess.run(
        ["bash", str(REPO / "deploy" / "bootstrap.sh")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr + r.stdout
