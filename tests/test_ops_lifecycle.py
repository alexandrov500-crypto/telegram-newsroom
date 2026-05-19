from __future__ import annotations

from pathlib import Path

from bot.ops_lifecycle.db_health import database_health
from bot.ops_lifecycle.policies import default_policies
from bot.ops_lifecycle.retention import RetentionEngine
from bot.ops_lifecycle.storage_report import build_ops_storage_payload
from bot.storage.db import init_database


def test_default_policies_cover_artifacts() -> None:
    names = {p.name for p in default_policies()}
    assert "runtime_pulses" in names
    assert "live_publish_trace" in names
    assert "editorial_story_events" in names


def test_retention_dry_run(tmp_path: Path) -> None:
    db = init_database(tmp_path / "lifecycle.db")
    engine = RetentionEngine(db)
    report = engine.run(dry_run=True, vacuum=False, backup=False)
    assert report.dry_run is True
    assert report.integrity_ok is True


def test_database_health(tmp_path: Path) -> None:
    db = init_database(tmp_path / "health.db")
    health = database_health(db)
    assert health["exists"] is True
    assert health["size_bytes"] > 0
    assert "pending_news" in health.get("tables", {})


def test_ops_storage_payload(tmp_path: Path) -> None:
    db = init_database(tmp_path / "storage.db")
    payload = build_ops_storage_payload(db)
    assert payload["status"] == "ok"
    assert "database" in payload
    assert "entropy" in payload
    assert "retention_policies" in payload
