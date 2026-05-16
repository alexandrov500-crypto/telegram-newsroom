"""Tests for read-only ops metrics snapshot tooling."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.ops_tooling import (
    OPS_SNAPSHOT_SCHEMA_VERSION,
    collect_diagnostics_payload,
    load_snapshot,
    persist_snapshot,
    rotate_snapshots,
    summarize_snapshots,
    build_timeline_report,
    timeline_report_markdown,
)


@pytest.fixture
def history(tmp_path: Path) -> Path:
    d = tmp_path / "ops_history"
    d.mkdir()
    return d


def test_persist_and_load_snapshot(history: Path) -> None:
    payload = {
        "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_kind": "ops_metrics",
        "read_only": True,
        "no_telegram_api_calls": True,
        "no_redis_mutations": True,
        "captured_at": "2026-05-16T12:00:00Z",
        "diagnostics": {
            "schema_version": 2,
            "read_only": True,
            "metrics": {"publish_retries": 1, "telethon_reconnects": 0},
            "retry_burst_window": 0,
            "status": "OK",
        },
    }
    path = persist_snapshot(history, payload, filename="ops_metrics_test.json")
    loaded = load_snapshot(path)
    assert loaded["captured_at"] == "2026-05-16T12:00:00Z"


def test_rotate_bounded(history: Path) -> None:
    for i in range(5):
        persist_snapshot(
            history,
            {
                "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
                "snapshot_kind": "ops_metrics",
                "read_only": True,
                "no_telegram_api_calls": True,
                "no_redis_mutations": True,
                "captured_at": f"2026-05-16T12:00:{i:02d}Z",
                "diagnostics": {"metrics": {"publishes": i}, "status": "OK"},
            },
            filename=f"ops_metrics_{i}.json",
        )
    rot = rotate_snapshots(history, max_files=3, max_total_bytes=10_000_000)
    assert rot["kept"] <= 3
    assert len(list(history.glob("ops_metrics_*.json"))) <= 3


def test_corrupt_snapshot_raises(history: Path) -> None:
    bad = history / "ops_metrics_bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt"):
        load_snapshot(bad)


def test_summarize_delta(history: Path) -> None:
    for n, pub in enumerate((0, 2, 5)):
        persist_snapshot(
            history,
            {
                "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
                "snapshot_kind": "ops_metrics",
                "read_only": True,
                "no_telegram_api_calls": True,
                "no_redis_mutations": True,
                "captured_at": f"2026-05-16T10:0{n}:00Z",
                "diagnostics": {"metrics": {"publishes": pub}},
            },
            filename=f"ops_metrics_a{n}.json",
        )
    s = summarize_snapshots(history)
    assert s["snapshot_count"] == 3
    assert s["counters"]["publishes"]["delta"] == 5


def test_collect_diagnostics_payload_read_only() -> None:
    with patch("tools.live_telegram_diagnostics.run_diagnostics") as m:
        m.return_value = {"read_only": True, "metrics": {}, "status": "OK"}
        doc = collect_diagnostics_payload()
    assert doc["read_only"] is True
    assert doc["no_redis_mutations"] is True


def test_timeline_report_offline(history: Path, tmp_path: Path) -> None:
    persist_snapshot(
        history,
        {
            "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_kind": "ops_metrics",
            "read_only": True,
            "no_telegram_api_calls": True,
            "no_redis_mutations": True,
            "captured_at": "2026-05-16T10:00:00Z",
            "diagnostics": {
                "metrics": {"telethon_flood_waits": 1, "publish_retries": 0},
            },
        },
        filename="ops_metrics_t0.json",
    )
    persist_snapshot(
        history,
        {
            "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_kind": "ops_metrics",
            "read_only": True,
            "no_telegram_api_calls": True,
            "no_redis_mutations": True,
            "captured_at": "2026-05-16T12:00:00Z",
            "diagnostics": {
                "metrics": {"telethon_flood_waits": 3, "publish_retries": 2},
            },
        },
        filename="ops_metrics_t1.json",
    )
    rt = tmp_path / "runtime"
    rt.mkdir()
    (rt / "operational_timeline.json").write_text(
        json.dumps(
            {
                "version": 1,
                "events": [{"ts": 1.0, "kind": "publication_ok", "payload": {"draft_id": 1}}],
            }
        ),
        encoding="utf-8",
    )
    report = build_timeline_report(history, runtime_dir=rt, limit=10)
    assert report["trend"]["telethon_flood_waits_delta"] == 2
    md = timeline_report_markdown(report)
    assert "FloodWait delta" in md


def test_cli_snapshot_roundtrip(history: Path, tmp_path: Path) -> None:
    import subprocess
    import sys

    out = tmp_path / "snap.json"
    proc = subprocess.run(
        [
            sys.executable,
            "tools/ops_metrics_snapshot.py",
            "--history-dir",
            str(history),
            "--json-output",
            str(out),
        ],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "written" in data
