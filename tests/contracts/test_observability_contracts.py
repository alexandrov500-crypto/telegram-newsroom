"""Observability tooling contracts — schema stability, no runtime drift."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from utils.ops_tooling import (
    OPS_SNAPSHOT_SCHEMA_VERSION,
    summarize_snapshots,
    validate_snapshot_document,
)

REPO = Path(__file__).resolve().parents[2]

ADR_030 = "docs/architecture/ADR-030-v3-2-operational-tooling-scope.md"


def test_adr_030_exists() -> None:
    assert (REPO / ADR_030).is_file()


def test_ops_snapshot_schema_version_stable() -> None:
    assert OPS_SNAPSHOT_SCHEMA_VERSION == 1


def test_snapshot_missing_optional_diagnostics_fields() -> None:
    doc = {
        "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
        "snapshot_kind": "ops_metrics",
        "read_only": True,
        "no_telegram_api_calls": True,
        "no_redis_mutations": True,
        "captured_at": "2026-05-16T00:00:00Z",
        "diagnostics": {"metrics": {"publishes": 1}},
    }
    assert validate_snapshot_document(doc) == []


def test_summarize_tolerates_sparse_metrics(tmp_path: Path) -> None:
    d = tmp_path / "hist"
    d.mkdir()
    (d / "ops_metrics_a.json").write_text(
        json.dumps(
            {
                "schema_version": OPS_SNAPSHOT_SCHEMA_VERSION,
                "snapshot_kind": "ops_metrics",
                "read_only": True,
                "no_telegram_api_calls": True,
                "no_redis_mutations": True,
                "captured_at": "2026-05-16T00:00:00Z",
                "diagnostics": {"metrics": {"publishes": 1}},
            }
        ),
        encoding="utf-8",
    )
    s = summarize_snapshots(d)
    assert s["counters"]["publishes"]["last"] == 1


def test_live_diagnostics_schema_v2_unchanged() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/live_telegram_diagnostics.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data.get("schema_version") == 2
    assert data.get("read_only") is True


def test_queue_introspection_cli_read_only_flags() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/queue_introspection.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data.get("read_only") is True
    assert data.get("no_redis_mutations") is True


def test_publisher_retry_semantics_unchanged() -> None:
    """Guard: publish retry attempts remain 3 (no v3.2 drift)."""
    import inspect

    from publisher.retry import async_retry

    src = inspect.getsource(async_retry)
    assert "attempts: int = 3" in src
    assert "inc(\"publish_retries\")" in src
