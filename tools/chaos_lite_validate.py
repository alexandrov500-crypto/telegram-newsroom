#!/usr/bin/env python3
"""Controlled chaos-lite validation — pytest subsets, no external chaos frameworks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Each entry: label, pytest path/expression, what it verifies
SCENARIOS: list[tuple[str, str, str]] = [
    (
        "telegram_retry",
        "tests/reliability/test_chaos_lite.py::test_chaos_publish_timeout_classified",
        "Telegram intermittent failure classified retryable; no blind abandon",
    ),
    (
        "openai_timeout",
        "tests/reliability/test_chaos_lite.py::test_chaos_openai_timeout_classified_retryable",
        "OpenAI timeout burst → retryable classification",
    ),
    (
        "stale_tick_recovery",
        "tests/reliability/test_chaos_lite.py::test_chaos_stale_tick_recovery",
        "VPS restart / scheduler pause → stale ticks recovered safely",
    ),
    (
        "lease_takeover",
        "tests/reliability/test_chaos_lite.py::test_chaos_stale_lease_takeover",
        "Execution lease stale takeover after simulated crash",
    ),
    (
        "publish_idempotency",
        "tests/test_ops_resilience.py::test_publish_journal_idempotency_record",
        "Same tick/draft cannot double-commit via journal idempotency key",
    ),
    (
        "continuity",
        "tests/test_public_readiness.py",
        "Continuity score, gates, operator feedback — no silent publish stop",
    ),
    (
        "runtime_protection",
        "tests/test_runtime_protection.py",
        "Degradation recovery; CRITICAL blocks autonomous publish",
    ),
    (
        "execution_graph",
        "tests/test_execution_graph_trace.py",
        "Execution graph consistency signals",
    ),
]


def main() -> int:
    p = argparse.ArgumentParser(description="Chaos-lite validation (in-process)")
    p.add_argument("--list", action="store_true", help="List scenarios")
    p.add_argument("--scenario", action="append", help="Run only named scenario(s)")
    args = p.parse_args()

    if args.list:
        for name, target, desc in SCENARIOS:
            print(f"{name}: {desc}\n  → pytest {target}\n")
        return 0

    selected = SCENARIOS
    if args.scenario:
        want = {s.strip().lower() for s in args.scenario}
        selected = [t for t in SCENARIOS if t[0].lower() in want]
        if not selected:
            print("Unknown scenario(s). Use --list.", file=sys.stderr)
            return 1

    python = sys.executable
    failed: list[str] = []
    print("=== Chaos-lite validation ===\n")
    for name, target, desc in selected:
        print(f"--- {name} ---")
        print(desc)
        cmd = [python, "-m", "pytest", target, "-q", "--tb=line"]
        proc = subprocess.run(cmd, cwd=str(REPO))
        if proc.returncode != 0:
            failed.append(name)
        print()

    if failed:
        print(f"FAIL: scenarios failed: {', '.join(failed)}")
        return 1
    print("PASS: all chaos-lite scenarios passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
