"""Repeated snapshot/restore cycles (inspection tree)."""

from __future__ import annotations

from pathlib import Path

from tests.soak.harness import simulate_snapshot_restore_cycle


def test_repeated_snapshot_restore_idempotent(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    src = repo / "examples/failure_drills/warning_optional_missing/runtime"
    od = tmp_path / "restore-cycle"
    for _ in range(3):
        assert simulate_snapshot_restore_cycle(od, src)
