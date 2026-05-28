"""Append-only ingestion ledger with state transitions."""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from ops.pipeline.paths import ingestion_ledger_path
from ops.pipeline.state_machine import NewsState, coerce_state, transition_allowed

_lock = threading.RLock()
_MAX_LINES = 20_000


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


class IngestionLedger:
    def __init__(self, runtime_dir: str | None) -> None:
        self._runtime_dir = runtime_dir

    def append(
        self,
        *,
        news_id: str,
        from_state: NewsState | str | None,
        to_state: NewsState | str,
        decision_reason: str = "",
        source: str = "",
        external_message_id: int | None = None,
        idempotency_key: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tgt = coerce_state(to_state)
        cur = coerce_state(from_state) if from_state is not None else None
        if cur is not None and not transition_allowed(cur, tgt):
            raise ValueError(f"illegal transition {cur.value} → {tgt.value}")

        entry: dict[str, Any] = {
            "id": f"led-{uuid.uuid4().hex[:16]}",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ts_unix": round(time.time(), 3),
            "runtime_id": _runtime_id(),
            "news_id": str(news_id)[:120],
            "from_state": cur.value if cur else None,
            "to_state": tgt.value,
            "decision_reason": (decision_reason or "")[:300],
            "source": (source or "")[:120],
            "external_message_id": external_message_id,
            "idempotency_key": (idempotency_key or "")[:160],
        }
        if extra:
            entry["extra"] = extra

        path = ingestion_ledger_path(self._runtime_dir)
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            _trim(path)
        return entry

    def latest_state(self, news_id: str) -> NewsState | None:
        for row in reversed(self.tail(limit=500)):
            if row.get("news_id") == news_id:
                return coerce_state(row.get("to_state"))
        return None

    def tail(self, *, limit: int = 100) -> list[dict[str, Any]]:
        path = ingestion_ledger_path(self._runtime_dir)
        if not path.is_file():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError:
            return []
        return rows[-limit:]


def _trim(path: Any) -> None:
    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= _MAX_LINES:
            return
        path.write_text("".join(lines[-_MAX_LINES:]), encoding="utf-8")
    except OSError:
        pass
