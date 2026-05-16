"""Evidence retention and manifest aging."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_evidence_report_cli(tmp_path: Path) -> None:
    od = tmp_path / "od"
    (od / "runtime").mkdir(parents=True)
    (od / "runtime" / "health_snapshot.json").write_text('{"schema_version":1}', encoding="utf-8")
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/evidence_retention.py"),
            "report",
            "--output-dir",
            str(od),
            "--json-output",
            str(out),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["runtime"]["files"] >= 1


def test_retention_prune_dry_run(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    for i in range(3):
        (art / f"qualification_{i}.json").write_text("{}", encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "tools/evidence_retention.py"),
            "prune",
            "--artifacts-dir",
            str(art),
            "--max-count",
            "1",
            "--dry-run",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert len(list(art.glob("*.json"))) == 3
