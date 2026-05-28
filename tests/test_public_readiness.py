"""Pre-public readiness, operator feedback, publish continuity."""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from app.editorial.operator_feedback import FeedbackAction, receive_operator_feedback
from app.observability.publish_continuity import (
    compute_autonomous_continuity_score,
    is_operator_autopublish_paused,
    set_operator_autopublish_pause,
)
from app.observability.prepublic_qa import prepublic_qa_enabled
from app.observability.public_readiness import evaluate_final_public_readiness
from app.observability.runtime_protection import (
    RuntimeHealthLevel,
    _transition,
    load_protection_state,
)
from app.ops.execution_gates import evaluate_publish_gate


@pytest.fixture
def settings(tmp_path, monkeypatch):
    from types import SimpleNamespace

    db = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    monkeypatch.setenv("RUNTIME_STATE_DIR", str(tmp_path))
    return SimpleNamespace(
        runtime_state_dir=str(tmp_path),
        global_publish_pause=False,
        database_url=f"sqlite+aiosqlite:///{db}",
    )


def _init_db(path):
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE pipeline_ticks (
          id INTEGER PRIMARY KEY, tick_id TEXT, status TEXT,
          started_at TEXT, finished_at TEXT, duration_ms INTEGER,
          detail_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE published_posts (
          id INTEGER PRIMARY KEY, draft_id INTEGER, telegram_post_id INTEGER,
          published_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE drafts (
          id INTEGER PRIMARY KEY, content TEXT, sources TEXT, status TEXT,
          created_at TEXT, published_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO published_posts (draft_id, telegram_post_id, published_at)
        VALUES (1, 99, datetime('now', '-1 hours'))
        """
    )
    conn.execute(
        """
        INSERT INTO pipeline_ticks (tick_id, status, started_at, finished_at, detail_json)
        VALUES ('t1', 'ok', datetime('now', '-2 hours'), datetime('now', '-1 hours'), '{}')
        """
    )
    conn.commit()
    conn.close()


def test_operator_feedback_suppress_source(settings, tmp_path, monkeypatch):
    from db.session import close_db, init_db

    url = f"sqlite+aiosqlite:///{tmp_path / 'feedback.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    async def _run() -> None:
        await init_db(url)
        try:
            fid, status = await receive_operator_feedback(
                settings=settings,
                operator_id=1,
                action=FeedbackAction.SUPPRESS_SOURCE.value,
                metadata={"channel": "@testchan"},
            )
            assert fid is not None
            assert status.startswith("applied")
        finally:
            await close_db()

    asyncio.run(_run())


def test_autopublish_pause(settings, tmp_path):
    assert not is_operator_autopublish_paused(str(tmp_path))
    set_operator_autopublish_pause(str(tmp_path), paused=True, operator_id=1)
    assert is_operator_autopublish_paused(str(tmp_path))


def test_continuity_score(settings, tmp_path):
    _init_db(tmp_path / "t.db")
    conn = sqlite3.connect(tmp_path / "t.db")
    out = compute_autonomous_continuity_score(conn, runtime_dir=str(tmp_path))
    conn.close()
    assert "autonomous_continuity_score" in out
    assert out["autonomous_continuity_score"] > 0


def test_publish_gate_integrity(settings, tmp_path):
    state = load_protection_state(str(tmp_path))
    _transition(str(tmp_path), state, RuntimeHealthLevel.CRITICAL, ["test"])
    gate = evaluate_publish_gate(settings, trace=False)
    assert gate.allowed is False
    assert "runtime_protection" in gate.layer or "critical" in gate.reason


def test_public_readiness_structure(settings, tmp_path):
    _init_db(tmp_path / "t.db")
    out = evaluate_final_public_readiness(
        db_path=tmp_path / "t.db",
        runtime_dir=tmp_path,
        log_path=tmp_path / "missing.log",
    )
    assert out["FINAL_PUBLIC_READINESS"] in {"NOT_READY", "CONDITIONAL", "READY"}


def test_prepublic_qa_env(monkeypatch):
    monkeypatch.delenv("PREPUBLIC_QA_MODE", raising=False)
    assert prepublic_qa_enabled() is False
    monkeypatch.setenv("PREPUBLIC_QA_MODE", "true")
    assert prepublic_qa_enabled() is True


def test_simulated_tick_burst_continuity(settings, tmp_path):
    """Lightweight burn-in: many recent ticks should not collapse continuity to zero."""
    _init_db(tmp_path / "t.db")
    conn = sqlite3.connect(tmp_path / "t.db")
    for i in range(12):
        conn.execute(
            """
            INSERT INTO pipeline_ticks (tick_id, status, started_at, finished_at, detail_json)
            VALUES (?, 'ok', datetime('now', ?), datetime('now'), '{}')
            """,
            (f"burst-{i}", f"-{i} minutes"),
        )
    conn.commit()
    out = compute_autonomous_continuity_score(conn, runtime_dir=str(tmp_path))
    conn.close()
    assert float(out["autonomous_continuity_score"]) >= 40.0


def test_openai_timeout_retry_classified() -> None:
    from app.reliability.failed_draft_recovery import is_publish_failure_retryable

    assert is_publish_failure_retryable(reason="APITimeoutError: request timed out") is True


def test_telegram_intermittent_retry_classified() -> None:
    from app.reliability.failed_draft_recovery import is_publish_failure_retryable

    assert is_publish_failure_retryable(reason="Bot timeout") is True


def test_operator_feedback_unknown_action_rejected(settings, tmp_path, monkeypatch):
    from db.session import close_db, init_db

    url = f"sqlite+aiosqlite:///{tmp_path / 'fb2.db'}"
    monkeypatch.setenv("DATABASE_URL", url)

    async def _run() -> None:
        await init_db(url)
        try:
            fid, status = await receive_operator_feedback(
                settings=settings,
                operator_id=1,
                action="not_a_real_action",
            )
            assert fid is None
            assert "rejected" in status
        finally:
            await close_db()

    asyncio.run(_run())
