"""Append-only editorial decision ledger (JSONL, bounded retention)."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from editorial.governance.paths import decision_ledger_path

_lock = threading.RLock()
_MAX_LINES = int(os.getenv("EDITORIAL_LEDGER_MAX_LINES", "5000"))
_MAX_BYTES = int(os.getenv("EDITORIAL_LEDGER_MAX_BYTES", str(8_000_000)))


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


def append_decision(
    *,
    runtime_dir: str | None,
    decision_type: str,
    outcome: str,
    subject_type: str = "cluster",
    subject_id: str = "",
    reason_codes: list[str] | None = None,
    ranking_trace: dict[str, Any] | None = None,
    scoring_components: dict[str, Any] | None = None,
    policy_matches: list[dict[str, Any]] | None = None,
    dedup: dict[str, Any] | None = None,
    publish: dict[str, Any] | None = None,
    operator_override: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one immutable record; returns the stored entry."""
    entry: dict[str, Any] = {
        "id": f"edl-{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_unix": round(time.time(), 3),
        "runtime_id": _runtime_id(),
        "decision_type": decision_type[:80],
        "outcome": outcome[:80],
        "subject_type": subject_type[:40],
        "subject_id": str(subject_id)[:120],
        "reason_codes": list(reason_codes or [])[:32],
        "ranking_trace": ranking_trace or {},
        "scoring_components": scoring_components or {},
        "policy_matches": list(policy_matches or [])[:24],
        "dedup": dedup or {},
        "publish": publish or {},
        "operator_override": operator_override or {},
    }
    if extra:
        entry["extra"] = extra
    path = decision_ledger_path(runtime_dir)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        _apply_retention(path)
    return entry


def _apply_retention(path: Path) -> None:
    if not path.is_file():
        return
    try:
        if path.stat().st_size <= _MAX_BYTES:
            with path.open(encoding="utf-8") as fh:
                lines = fh.readlines()
            if len(lines) <= _MAX_LINES:
                return
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        keep = lines[-_MAX_LINES:]
        while keep and sum(len(x.encode()) for x in keep) > _MAX_BYTES:
            keep = keep[1:]
        path.write_text("".join(keep), encoding="utf-8")
    except OSError:
        pass


def query_decisions(
    runtime_dir: str | None,
    *,
    limit: int = 100,
    decision_type: str | None = None,
    subject_id: str | None = None,
) -> list[dict[str, Any]]:
    path = decision_ledger_path(runtime_dir)
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
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
                if not isinstance(row, dict):
                    continue
                if decision_type and row.get("decision_type") != decision_type:
                    continue
                if subject_id and row.get("subject_id") != subject_id:
                    continue
                out.append(row)
    except OSError:
        return []
    return list(reversed(out[-limit:]))


def reset_ledger_for_tests(runtime_dir: str) -> None:
    p = decision_ledger_path(runtime_dir)
    if p.is_file():
        p.unlink()
