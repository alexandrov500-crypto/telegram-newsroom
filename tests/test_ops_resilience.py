"""Operational resilience: snapshot, journal, migrations, modes, leadership."""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from app.operational_mode import OperationalMode, load_operational_mode, publish_allowed, set_operational_mode
from ops.resilience.leadership import LeadershipCoordinator
from ops.resilience.migrations import apply_runtime_migrations, migrations_payload
from ops.resilience.publish_journal import (
    append_journal,
    find_finalized_for_draft,
    new_publish_tx_id,
    reset_journal_for_tests,
)
from ops.resilience.snapshot import create_snapshot, restore_snapshot


def test_publish_journal_idempotency_record(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    reset_journal_for_tests(rd)
    tx = new_publish_tx_id()
    append_journal(rd, tx_id=tx, draft_id=42, state="initiated", idempotency_key="draft:42")
    append_journal(
        rd,
        tx_id=tx,
        draft_id=42,
        state="finalized",
        idempotency_key="draft:42",
        channel_message_id=999,
    )
    row = find_finalized_for_draft(rd, 42)
    assert row is not None
    assert row["channel_message_id"] == 999


def test_snapshot_create_restore_roundtrip(ephemeral_newsroom_settings, tmp_path: Path) -> None:
    rd = Path(ephemeral_newsroom_settings.runtime_state_dir)
    (rd / "editorial").mkdir(parents=True, exist_ok=True)
    (rd / "editorial" / "governance_rules.json").write_text('{"version":1,"rules":[]}', encoding="utf-8")
    archive = create_snapshot(
        runtime_dir=str(rd),
        database_url=ephemeral_newsroom_settings.database_url,
    )
    assert archive.is_file()
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "MANIFEST.json" in names

    target = tmp_path / "restored_runtime"
    target.mkdir()
    report = restore_snapshot(
        archive,
        runtime_dir=str(target),
        database_url="sqlite:///:memory:",
        dry_run=True,
    )
    assert report["restored_files"] >= 1


def test_migrations_idempotent(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    a = apply_runtime_migrations(rd)
    b = apply_runtime_migrations(rd)
    assert b["applied_now"] == []
    payload = migrations_payload(rd)
    assert "registered" in payload


def test_operational_mode_publish_blocked(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    set_operational_mode(rd, OperationalMode.READ_ONLY, reason="test")
    mode = load_operational_mode(rd)
    assert not publish_allowed(mode, ephemeral_newsroom_settings)
    set_operational_mode(rd, OperationalMode.PRODUCTION, reason="test_reset")


def test_leadership_acquire_release(ephemeral_newsroom_settings) -> None:
    coord = LeadershipCoordinator(ephemeral_newsroom_settings.runtime_state_dir)
    assert coord.runtime.acquire(runtime_id="test-runtime")
    coord.runtime.release()
