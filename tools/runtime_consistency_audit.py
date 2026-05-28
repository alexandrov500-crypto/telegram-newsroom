#!/usr/bin/env python3
"""Audit: duplicate processes, singleton lock, active runtime, code identity."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _pgrep(pattern: str) -> list[str]:
    try:
        out = subprocess.run(
            ["pgrep", "-fl", pattern],
            capture_output=True,
            text=True,
            check=False,
        )
        return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    except OSError:
        return []


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (out.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def main() -> int:
    runtime_dir = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    issues: list[str] = []
    report: dict[str, object] = {}

    print("== Process scan (app.main) ==")
    main_hits = _pgrep("app.main")
    report["app_main_processes"] = main_hits
    for h in main_hits:
        print(f"  {h}")
    if len(main_hits) > 1:
        issues.append(f"multiple app.main processes: {len(main_hits)}")
    if not main_hits:
        print("  (none)")

    print("\n== Lock / active runtime ==")
    lock = Path(runtime_dir) / "newsroom.lock"
    active = Path(runtime_dir) / "active_runtime.json"
    report["singleton_lock_path"] = str(lock)
    report["singleton_lock_exists"] = lock.is_file()
    if lock.is_file():
        body = lock.read_text(encoding="utf-8")[:500]
        print(body)
        report["singleton_lock_body"] = body
    active_data: dict | None = None
    if active.is_file():
        try:
            active_data = json.loads(active.read_text(encoding="utf-8"))
            print(json.dumps(active_data, indent=2))
            report["active_runtime"] = active_data
            apid = int(active_data.get("pid") or 0)
            if apid and not _pid_alive(apid):
                issues.append(f"stale active_runtime.json pid={apid} (process dead)")
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"active_runtime unreadable: {exc}")

    print("\n== Code identity ==")
    try:
        from app.build_provenance import load_build_provenance
        import publisher.telegram_transport as tt
        import publisher.telegram_forensic as tf
        from publisher.telegram_forensic import bot_token_fingerprint, forensic_media_enabled

        prov = load_build_provenance()
        token = os.getenv("BOT_TOKEN", "")
        identity = {
            "git_sha_env": prov.git_sha,
            "git_sha_repo": _git_head(),
            "transport_module": tt.__file__,
            "forensic_module": tf.__file__,
            "forensic_media_enabled": forensic_media_enabled(),
            "cwd": os.getcwd(),
            "bot_token_fingerprint": bot_token_fingerprint(token) if token else "unset",
        }
        report["code_identity"] = identity
        print(json.dumps(identity, indent=2))
        if prov.git_sha == "unknown" and identity["git_sha_repo"] != "unknown":
            print("NOTE: set NEWSROOM_GIT_SHA in deploy env for runtime traceability")
    except Exception as exc:
        issues.append(f"code_identity: {exc}")
        print(f"ERROR: {exc}")

    print("\n== Polling owner hint ==")
    if active_data:
        apid = int(active_data.get("pid") or 0)
        alive = _pid_alive(apid)
        print(f"active_runtime pid={apid} alive={alive}")
        report["polling_owner_pid_alive"] = alive
        if main_hits and apid:
            main_pids = []
            for line in main_hits:
                parts = line.split(maxsplit=1)
                if parts:
                    try:
                        main_pids.append(int(parts[0]))
                    except ValueError:
                        pass
            if main_pids and apid not in main_pids:
                issues.append(f"active_runtime pid {apid} not in app.main list {main_pids}")

    print("\n== Verdict ==")
    if issues:
        for i in issues:
            print(f"FAIL: {i}")
        return 1
    print("OK — single-runtime check passed locally; confirm VPS not polling same BOT_TOKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
