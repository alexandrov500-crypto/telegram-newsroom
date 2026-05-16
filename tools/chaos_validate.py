#!/usr/bin/env python3
"""Run chaos test suite and print summary (diagnostic utility; no prod side effects)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run tests/chaos and optional sanity check")
    parser.add_argument("--pytest-args", default="-q --tb=short", help="Extra pytest arguments")
    parser.add_argument("--skip-sanity", action="store_true")
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "pytest", "tests/chaos", *args.pytest_args.split()]
    print("==> chaos suite:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO))
    if proc.returncode != 0:
        return proc.returncode

    if not args.skip_sanity:
        drill = REPO / "examples/failure_drills/warning_optional_missing"
        if drill.is_dir():
            sanity = subprocess.run(
                ["bash", str(REPO / "scripts/runtime_sanity_check.sh")],
                cwd=str(REPO),
                env={**dict(**__import__("os").environ), "OUTPUT_DIR": str(drill), "STRICT": "0"},
            )
            if sanity.returncode != 0:
                print("sanity check failed on warning drill", file=sys.stderr)
                return sanity.returncode
            print("==> sanity check: OK")

    print("==> chaos validation: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
