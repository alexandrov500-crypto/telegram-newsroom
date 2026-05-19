#!/usr/bin/env python3
"""Detect duplicate newsroom operator processes and stale runtime artifacts."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.config import bootstrap_env, project_root
from bot.runtime.ownership import RuntimeOwnershipLock, read_lock_holder


@dataclass
class RuntimeProcess:
    pid: int
    profile: str
    started: str
    command: str
    source: str
    stale: bool = False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _profile_guess(cmd: str) -> str:
    if "RUNTIME_PROFILE=minimal_pilot" in cmd or "minimal_pilot" in cmd:
        return "minimal_pilot"
    if "research_full" in cmd:
        return "research_full"
    if "standard_live" in cmd:
        return "standard_live"
    return "unknown"


def _scan_ps() -> list[RuntimeProcess]:
    patterns = ("bot.main", "-m bot.main", "bot/main.py")
    try:
        out = subprocess.check_output(
            ["ps", "-eo", "pid=,lstart=,command="],
            text=True,
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []

    rows: list[RuntimeProcess] = []
    for line in out.splitlines():
        if not any(p in line for p in patterns):
            continue
        if "runtime_process_check" in line or "grep" in line:
            continue
        m = re.match(r"\s*(\d+)\s+(\w{3}\s+\w{3}\s+\d+\s+[\d:]+\s+\d+)\s+(.*)$", line)
        if not m:
            m2 = re.match(r"\s*(\d+)\s+(.*)$", line)
            if not m2:
                continue
            pid = int(m2.group(1))
            cmd = m2.group(2).strip()
            started = "unknown"
        else:
            pid = int(m.group(1))
            started = m.group(2).strip()
            cmd = m.group(3).strip()
        rows.append(
            RuntimeProcess(
                pid=pid,
                profile=_profile_guess(cmd),
                started=started,
                command=cmd[:120],
                source="ps",
            ),
        )
    return rows


def _pid_file_entries() -> list[tuple[str, int]]:
    paths = [
        project_root() / "var" / "run" / "pilot-operator.pid",
        Path(os.getenv("PILOT_PID_FILE", "")).expanduser(),
    ]
    found: list[tuple[str, int]] = []
    seen: set[Path] = set()
    for path in paths:
        if not path or not str(path) or path in seen:
            continue
        seen.add(path)
        if path.is_file():
            try:
                found.append((str(path), int(path.read_text().strip())))
            except (ValueError, OSError):
                found.append((str(path), -1))
    return found


def _docker_operator_containers() -> list[str]:
    if not shutil_which("docker"):
        return []
    try:
        out = subprocess.check_output(
            [
                "docker",
                "ps",
                "--format",
                "{{.ID}}\t{{.Names}}\t{{.Status}}",
            ],
            text=True,
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return []
    lines = []
    for row in out.splitlines():
        if "operator" in row.lower() or "newsroom" in row.lower():
            lines.append(row)
    return lines


def shutil_which(cmd: str) -> str | None:
    from shutil import which

    return which(cmd)


def main() -> int:
    bootstrap_env()
    lock_path = RuntimeOwnershipLock.default_path()
    holder = read_lock_holder(lock_path)
    processes = _scan_ps()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    print("=" * 56)
    print(" NEWSROOM RUNTIME PROCESS CHECK")
    print(f" {now}")
    print("=" * 56)
    print()

    if holder:
        lock_pid = int(holder.get("pid", 0) or 0)
        alive = _pid_alive(lock_pid) if lock_pid else False
        print("LOCK FILE:", lock_path)
        print(f"  instance={holder.get('runtime_instance_id', '?')}")
        print(f"  pid={lock_pid} alive={alive}")
        print(f"  profile={holder.get('runtime_profile', '?')}")
        print(f"  started_at={holder.get('started_at', '?')}")
        print()
    else:
        print("LOCK FILE: none (no active holder recorded)")
        print()

    pid_files = _pid_file_entries()
    if pid_files:
        print("PID FILES:")
        for path, pid in pid_files:
            alive = _pid_alive(pid) if pid > 0 else False
            tag = "STALE" if pid > 0 and not alive else ("ACTIVE" if alive else "INVALID")
            print(f"  [{tag}] {path} -> pid={pid}")
        print()

    docker_rows = _docker_operator_containers()
    if docker_rows:
        print("DOCKER OPERATOR CONTAINERS:")
        for row in docker_rows:
            print(f"  {row}")
        print()

    if not processes:
        print("ACTIVE RUNTIMES: none detected (ps)")
    else:
        print("ACTIVE RUNTIMES:")
        if len(processes) > 1:
            print("  WARNING: multiple operator processes detected")
        ordered = sorted(processes, key=lambda p: p.pid)
        for i, proc in enumerate(ordered):
            stale = len(ordered) > 1 and i < len(ordered) - 1
            tag = "  <-- STALE?" if stale else ""
            print(
                f"  PID {proc.pid:>6}  {proc.profile:<16}  started {proc.started}{tag}",
            )
            print(f"           {proc.command}")
    print()

    if holder:
        lock_pid = int(holder.get("pid", 0) or 0)
        if lock_pid and not any(p.pid == lock_pid for p in processes):
            alive = _pid_alive(lock_pid)
            print(
                f"NOTE: lock holder pid={lock_pid} not in ps list (alive={alive})",
            )
            print()

    if len(processes) > 1:
        print("RESULT: FAIL — duplicate runtimes")
        print("ACTION: bash scripts/kill_all_operator_processes.sh")
        return 1
    if holder:
        lock_pid = int(holder.get("pid", 0) or 0)
        if lock_pid and processes and lock_pid != processes[0].pid:
            print("RESULT: WARN — lock pid does not match sole ps process")
            return 1
    print("RESULT: OK — single runtime (or none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
