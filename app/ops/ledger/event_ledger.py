"""Append-only event ledger — audit/replay source of truth for ingestion."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_NAME = "event_ledger.db"
_JSONL_NAME = "ledger.jsonl"
_ledger: EventLedger | None = None
_runtime_dir: str | None = None
_lock = threading.RLock()


class EventType(str, Enum):
    INGESTED = "INGESTED"
    ROUTED = "ROUTED"
    DROPPED = "DROPPED"
    PUBLISHED = "PUBLISHED"


def event_fingerprint(channel: str, message_id: int) -> str:
    """Stable dedup key: hash(channel + message_id)."""
    from app.ingestion.idempotency import message_fingerprint

    return message_fingerprint(channel, message_id)


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


@dataclass
class LedgerEvent:
    event_type: EventType | str
    channel: str
    message_id: int
    fingerprint: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    runtime_id: str = ""
    timestamp: str = ""
    timestamp_unix: float = 0.0

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.runtime_id:
            self.runtime_id = _runtime_id()
        if self.timestamp_unix <= 0:
            self.timestamp_unix = time.time()
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp_unix))
        if isinstance(self.event_type, str):
            self.event_type = EventType(self.event_type.upper())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = (
            self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type)
        )
        return d


class EventLedger:
    """SQLite append-only ledger with fingerprint dedup index."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    runtime_id TEXT NOT NULL,
                    timestamp_unix REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_fp ON events(fingerprint)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    fingerprint TEXT PRIMARY KEY,
                    first_event_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    ingested_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS replay_cursor (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    last_event_id TEXT,
                    updated_at REAL
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO replay_cursor (id, last_event_id, updated_at) VALUES (1, NULL, 0)"
            )

    def is_duplicate_event(self, fingerprint: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM fingerprints WHERE fingerprint = ? LIMIT 1",
                (fingerprint,),
            ).fetchone()
        return row is not None

    def append(self, event: LedgerEvent, *, claim_fingerprint: bool = False) -> str:
        """
        Append immutable event. If claim_fingerprint=True (INGESTED), register fingerprint atomically.
        Returns event_id; raises ValueError if fingerprint already claimed when claim requested.
        """
        et = (
            event.event_type.value
            if isinstance(event.event_type, EventType)
            else str(event.event_type).upper()
        )
        payload_json = json.dumps(event.payload, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if claim_fingerprint:
                    cur = conn.execute(
                        """
                        INSERT OR IGNORE INTO fingerprints
                            (fingerprint, first_event_id, channel, message_id, ingested_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            event.fingerprint,
                            event.event_id,
                            (event.channel or "").strip().lower(),
                            int(event.message_id),
                            event.timestamp_unix,
                        ),
                    )
                    if cur.rowcount == 0:
                        raise ValueError("fingerprint_already_claimed")
                conn.execute(
                    """
                    INSERT INTO events
                        (event_id, runtime_id, timestamp_unix, timestamp, channel,
                         message_id, event_type, fingerprint, payload_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.runtime_id,
                        event.timestamp_unix,
                        event.timestamp,
                        (event.channel or "")[:200],
                        int(event.message_id),
                        et,
                        event.fingerprint,
                        payload_json,
                    ),
                )
                conn.execute("COMMIT")
            except ValueError:
                conn.execute("ROLLBACK")
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise
        self._mirror_jsonl(event.to_dict())
        return event.event_id

    def _mirror_jsonl(self, row: dict[str, Any]) -> None:
        """Append-only JSONL audit mirror (one line per event, crash-safe line boundary)."""
        global _runtime_dir
        if not _runtime_dir:
            return
        path = Path(_runtime_dir).expanduser().resolve() / _JSONL_NAME
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            logger.warning("ledger jsonl mirror failed: %s", exc)

    def count_by_type(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
            ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    def total_events(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return int(row[0]) if row else 0

    def fetch_ingested_for_replay(
        self,
        *,
        after_event_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Ordered INGESTED events for deterministic replay."""
        with self._connect() as conn:
            if after_event_id:
                row = conn.execute(
                    "SELECT timestamp_unix FROM events WHERE event_id = ?",
                    (after_event_id,),
                ).fetchone()
                if row:
                    rows = conn.execute(
                        """
                        SELECT event_id, runtime_id, timestamp, timestamp_unix, channel,
                               message_id, fingerprint, payload_json
                        FROM events
                        WHERE event_type = 'INGESTED' AND timestamp_unix > ?
                        ORDER BY timestamp_unix ASC, event_id ASC
                        LIMIT ?
                        """,
                        (float(row[0]), limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT event_id, runtime_id, timestamp, timestamp_unix, channel,
                               message_id, fingerprint, payload_json
                        FROM events
                        WHERE event_type = 'INGESTED'
                        ORDER BY timestamp_unix ASC, event_id ASC
                        LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT event_id, runtime_id, timestamp, timestamp_unix, channel,
                           message_id, fingerprint, payload_json
                    FROM events
                    WHERE event_type = 'INGESTED'
                    ORDER BY timestamp_unix ASC, event_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                payload = json.loads(r[7]) if r[7] else {}
            except json.JSONDecodeError:
                payload = {}
            out.append(
                {
                    "event_id": r[0],
                    "runtime_id": r[1],
                    "timestamp": r[2],
                    "timestamp_unix": r[3],
                    "channel": r[4],
                    "message_id": r[5],
                    "fingerprint": r[6],
                    "payload": payload,
                }
            )
        return out

    def get_replay_cursor(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_event_id FROM replay_cursor WHERE id = 1"
            ).fetchone()
        if row and row[0]:
            return str(row[0])
        return None

    def set_replay_cursor(self, event_id: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE replay_cursor SET last_event_id = ?, updated_at = ? WHERE id = 1",
                (event_id, time.time()),
            )


def init_event_ledger(runtime_dir: str) -> EventLedger:
    global _ledger, _runtime_dir
    with _lock:
        rd = str(Path(runtime_dir).expanduser().resolve())
        _runtime_dir = rd
        path = Path(rd) / _DB_NAME
        _ledger = EventLedger(path)
        logger.info("event ledger ready path=%s jsonl=%s", path, Path(rd) / _JSONL_NAME)
        return _ledger


def get_event_ledger() -> EventLedger | None:
    return _ledger


def is_duplicate_event(fingerprint: str) -> bool:
    ledger = get_event_ledger()
    if ledger is None:
        return False
    return ledger.is_duplicate_event(fingerprint)


def reset_event_ledger_for_tests() -> None:
    global _ledger, _runtime_dir
    with _lock:
        _ledger = None
        _runtime_dir = None
