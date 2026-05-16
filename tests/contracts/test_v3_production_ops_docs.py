"""Production operations docs and diagnostics contracts (v3 merge prep)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

OPS_DOCS = (
    "docs/operations/retry_error_matrix.md",
    "docs/operations/publish_idempotency.md",
    "docs/architecture/live_validation_runtime_flow.md",
)


@pytest.mark.parametrize("rel", OPS_DOCS)
def test_production_ops_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_retry_matrix_has_classification_table() -> None:
    text = (REPO / OPS_DOCS[0]).read_text(encoding="utf-8")
    assert "| Error Type | Retry? |" in text


def test_live_diagnostics_schema_v2_fields() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/live_telegram_diagnostics.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data.get("schema_version") == 2
    assert data.get("read_only") is True
    assert "operational" in data
    assert "publish_outcomes" in data["operational"]
    assert "telethon_flood_waits" in data["metrics"]
