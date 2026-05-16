"""Smoke tests for bounded health snapshot (no network, no Redis)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from observability.health_snapshot import (
    SNAPSHOT_KEY_ORDER,
    build_health_snapshot,
    default_health_snapshot_path,
    load_health_snapshot,
    render_health_summary,
    write_health_snapshot,
)

REPO = Path(__file__).resolve().parents[2]


def _minimal_ops_report(*, status: str = "OK") -> dict:
    return {
        "command": "nightly-check",
        "completed_at": "2026-05-15T12:00:01Z",
        "started_at": "2026-05-15T12:00:00Z",
        "status": status,
        "steps": [
            {"name": "preflight", "status": "OK"},
            {"name": "benchmark", "status": "OK"},
        ],
    }


def test_snapshot_schema_and_deterministic_keys(tmp_path: Path) -> None:
    snap = build_health_snapshot(
        ops_report=_minimal_ops_report(),
        output_dir=tmp_path,
        benchmark={
            "metrics_export": {
                "counters": {
                    "posts_collected": 128,
                    "clusters_created": 40,
                    "drafts_generated": 17,
                    "publishes": 10,
                    "drafts_published": 2,
                },
            },
        },
        qualification={"qualification_status": "OK"},
    )
    assert list(snap.keys()) == list(SNAPSHOT_KEY_ORDER)
    assert snap["collected_articles"] == 128
    assert snap["generated_drafts"] == 17
    assert snap["published_posts"] == 12
    assert snap["qualification_status"] == "OK"
    blob = json.dumps(snap, sort_keys=True)
    assert blob == json.dumps(dict(sorted(snap.items())), sort_keys=True)


def test_atomic_write_and_load(tmp_path: Path) -> None:
    out = tmp_path / "out"
    path = default_health_snapshot_path(out)
    snap = build_health_snapshot(ops_report=_minimal_ops_report(), output_dir=out)
    write_health_snapshot(path, snap)
    assert path.is_file()
    assert not path.with_name(path.name + ".tmp").exists()
    loaded = load_health_snapshot(path)
    assert loaded is not None
    assert loaded["pipeline_status"] == "OK"


def test_failed_steps_captured(tmp_path: Path) -> None:
    rep = _minimal_ops_report(status="FAIL")
    rep["steps"] = [
        {"name": "preflight", "status": "OK"},
        {"name": "bundle", "status": "FAIL"},
    ]
    snap = build_health_snapshot(ops_report=rep, output_dir=tmp_path)
    assert snap["failed_steps"] == ["bundle"]


def test_render_health_summary_smoke() -> None:
    snap = build_health_snapshot(
        ops_report=_minimal_ops_report(),
        benchmark={
            "metrics_export": {
                "counters": {"posts_collected": 128, "drafts_generated": 17, "publishes": 12},
            },
        },
    )
    txt = render_health_summary(snap)
    assert "Pipeline status: OK" in txt
    assert "Collected articles: 128" in txt
    assert "Runtime duration:" in txt


def test_cli_health_command_smoke(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    snap_path = default_health_snapshot_path(out)
    write_health_snapshot(snap_path, build_health_snapshot(ops_report=_minimal_ops_report(), output_dir=out))

    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "health", "--path", str(out)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "Pipeline status: OK" in proc.stdout
    assert "Collected articles:" in proc.stdout

    proc_json = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "health", "--path", str(snap_path), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert proc_json.returncode == 0
    data = json.loads(proc_json.stdout)
    assert data["pipeline_status"] == "OK"
