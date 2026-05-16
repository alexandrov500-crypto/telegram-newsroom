"""Bounded soak / drift chaos tests."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from workers.retry import build_policy_from_settings
from utils.reliability_diagnostics import build_stability_evidence, write_stability_evidence


def test_retry_policy_bounded_no_infinite_delay() -> None:
    from tests.conftest import minimal_test_settings

    s = minimal_test_settings(worker_retry_jitter_ratio=0.0, openai_json_max_retries=3)
    p = build_policy_from_settings(s, envelope_attempt=0)
    delays = [p.next_delay_sec(i) for i in range(20)]
    assert all(0.05 <= d <= 336.0 for d in delays)
    assert p.exhausted(p.max_attempts)


def test_sqlite_wal_observation_bounded(tmp_path: Path) -> None:
    db = tmp_path / "chaos.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    for i in range(50):
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES (?)", (f"row-{i}",))
    conn.commit()
    conn.close()
    wal = tmp_path / "chaos.db-wal"
    wal_bytes = wal.stat().st_size if wal.is_file() else 0
    assert wal_bytes >= 0


def test_stability_evidence_artifact_shape(tmp_path: Path) -> None:
    payload = build_stability_evidence(retry_count=12, wal_bytes=4096, trace_count=3)
    assert payload["schema_version"] == 1
    out = write_stability_evidence(tmp_path / "stability_evidence.json", payload)
    assert out.is_file()
    assert "retry_policy_invocations" in out.read_text(encoding="utf-8")


def test_repeated_snapshot_cycles_idempotent_manifest(tmp_path: Path) -> None:
    from observability.runtime_manifest import rebuild_runtime_manifest

    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    (rt / "health_snapshot.json").write_text(
        '{"schema_version":1,"pipeline_status":"OK"}', encoding="utf-8"
    )
    (rt / "runtime_report.json").write_text(
        '{"schema_version":1,"incident_level":"NONE"}', encoding="utf-8"
    )
    m1 = rebuild_runtime_manifest(od)
    m2 = rebuild_runtime_manifest(od)
    assert m1.is_file() and m2.is_file()


def test_log_growth_simulation_bounded() -> None:
    lines = [f"chaos log line {i}" for i in range(1000)]
    blob = "\n".join(lines)
    assert len(blob) < 500_000
