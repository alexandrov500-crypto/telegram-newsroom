#!/usr/bin/env python3
"""Run soak + drift validation (bounded CI gate)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--extended", action="store_true", help="Run extended soak marker (same tests, env hint)")
    p.add_argument("--pytest-args", default="-q --tb=short")
    args = p.parse_args()

    env = {**os.environ}
    if args.extended:
        env["SOAK_EXTENDED"] = "1"

    for label, path in (
        ("soak", "tests/soak"),
        ("drift", "tests/soak/test_drift_monitor.py"),
    ):
        cmd = [sys.executable, "-m", "pytest", path, *args.pytest_args.split()]
        print(f"==> {label}:", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(REPO), env=env)
        if proc.returncode != 0:
            return proc.returncode

    print("==> soak validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
