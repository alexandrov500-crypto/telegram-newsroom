#!/usr/bin/env python3
"""
Production verification: single-runtime lock, active_runtime.json, idempotent ingestion.

Run on VPS (host or inside container):

  docker exec telegram-ai-newsroom python /app/tools/verify_single_runtime.py
  docker exec telegram-ai-newsroom python /app/tools/verify_single_runtime.py --strict

After restart test:

  docker restart telegram-ai-newsroom && sleep 5
  docker exec telegram-ai-newsroom python /app/tools/verify_single_runtime.py --strict
  docker logs telegram-ai-newsroom 2>&1 | grep -E 'runtime_id=|Newsroom started|Not singleton' | tail -20
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _check_active_runtime(runtime_dir: Path) -> dict[str, Any]:
    path = runtime_dir / "active_runtime.json"
    out: dict[str, Any] = {"path": str(path), "ok": False}
    if not path.is_file():
        out["error"] = "missing"
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        out["error"] = repr(exc)
        return out
    if not isinstance(data, dict):
        out["error"] = "invalid_json"
        return out
    pid = int(data.get("pid", 0))
    out.update(
        {
            "runtime_id": data.get("runtime_id"),
            "pid": pid,
            "hostname": data.get("hostname"),
            "started_at": data.get("started_at"),
            "pid_alive": _pid_alive(pid),
        }
    )
    out["ok"] = bool(data.get("runtime_id")) and out["pid_alive"]
    return out


def _check_lock(runtime_dir: Path, expected_pid: int | None) -> dict[str, Any]:
    path = runtime_dir / "newsroom.lock"
    out: dict[str, Any] = {"path": str(path), "ok": False}
    if not path.is_file():
        out["error"] = "missing (no singleton owner or RUNTIME_SINGLETON_DISABLED)"
        out["ok"] = True  # not fatal if bypassed in dev
        return out
    try:
        raw = path.read_text(encoding="utf-8").strip()
        data = json.loads(raw) if raw.startswith("{") else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    pid = int(data.get("pid", 0))
    out["lock_pid"] = pid
    out["pid_alive"] = _pid_alive(pid)
    if expected_pid and pid and pid != expected_pid:
        out["error"] = f"lock_pid={pid} != active_runtime.pid={expected_pid}"
        return out
    out["ok"] = out["pid_alive"]
    return out


def _check_idempotency(runtime_dir: Path) -> dict[str, Any]:
    db = runtime_dir / "ingestion_idempotency.db"
    out: dict[str, Any] = {"path": str(db), "ok": True, "count": 0}
    if not db.is_file():
        out["note"] = "db not created yet (no ingests since deploy)"
        return out
    try:
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT COUNT(*) FROM processed_messages").fetchone()
        out["count"] = int(row[0]) if row else 0
        conn.close()
    except sqlite3.Error as exc:
        out["ok"] = False
        out["error"] = repr(exc)
    return out


def _check_db_duplicates(db_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {"path": str(db_path), "ok": True}
    if not db_path.is_file():
        out["skipped"] = True
        return out
    conn = sqlite3.connect(str(db_path))
    try:
        dup_raw = conn.execute(
            """
            SELECT channel_name, message_id, COUNT(*) AS c
            FROM raw_posts
            GROUP BY channel_name, message_id
            HAVING c > 1
            LIMIT 10
            """
        ).fetchall()
        out["duplicate_raw_posts"] = [{"channel": r[0], "message_id": r[1], "count": r[2]} for r in dup_raw]
        out["ok"] = len(dup_raw) == 0
        if dup_raw:
            out["error"] = f"{len(dup_raw)} duplicate raw_post keys (should be 0 — DB unique constraint)"
    except sqlite3.Error as exc:
        out["ok"] = False
        out["error"] = repr(exc)
    finally:
        conn.close()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Verify single-runtime + idempotent ingestion")
    p.add_argument("--runtime-dir", type=Path, default=None, help="default: RUNTIME_STATE_DIR or /data/runtime")
    p.add_argument("--db-path", type=Path, default=None, help="SQLite DB (default: /data/newsroom.db on VPS)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="exit 1 if any critical check fails")
    args = p.parse_args()

    runtime_dir = args.runtime_dir
    if runtime_dir is None:
        runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "/data/runtime"))
    runtime_dir = runtime_dir.expanduser().resolve()

    db_path = args.db_path
    if db_path is None:
        db_path = Path(os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/newsroom.db").split("///")[-1])

    report: dict[str, Any] = {
        "runtime_dir": str(runtime_dir),
        "checks": {
            "active_runtime": _check_active_runtime(runtime_dir),
            "idempotency_store": _check_idempotency(runtime_dir),
            "db_duplicate_raw_posts": _check_db_duplicates(db_path),
        },
    }
    ar = report["checks"]["active_runtime"]
    report["checks"]["newsroom_lock"] = _check_lock(
        runtime_dir,
        int(ar.get("pid", 0)) if ar.get("pid") else None,
    )

    critical = ["active_runtime", "newsroom_lock", "db_duplicate_raw_posts"]
    failed = [k for k in critical if not report["checks"].get(k, {}).get("ok", False)]
    report["overall_ok"] = len(failed) == 0
    report["failed"] = failed

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("=== Single-runtime verification ===")
        print(f"runtime_dir: {runtime_dir}")
        for name, chk in report["checks"].items():
            status = "OK" if chk.get("ok", False) else "FAIL"
            print(f"  [{status}] {name}")
            for key in ("runtime_id", "pid", "pid_alive", "count", "error", "note", "duplicate_raw_posts"):
                if key in chk and chk[key] not in (None, "", []):
                    print(f"       {key}: {chk[key]}")
        print(f"overall_ok: {report['overall_ok']}")
        if failed:
            print(f"failed: {', '.join(failed)}")

    if args.strict and not report["overall_ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
