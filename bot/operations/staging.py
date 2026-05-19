from __future__ import annotations

import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.operations.staging_runtime import StagingRuntimeValidator


def run_staging_validation(ops: Any) -> int:
    """Staging readiness checks (health endpoints, feed smoke, DB)."""
    failures: list[str] = []
    lines: list[str] = []

    smoke = StagingRuntimeValidator().run_all()
    for check in smoke:
        lines.append(f"[{'PASS' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
        if not check.passed:
            failures.append(f"smoke:{check.name}")

    health_url = os.getenv("STAGING_HEALTH_URL", "http://127.0.0.1:8080/health")
    try:
        with urllib.request.urlopen(health_url, timeout=5) as resp:
            if resp.status != 200:
                failures.append(f"health status {resp.status}")
    except Exception as exc:
        failures.append(f"health unreachable: {exc}")

    feeds = ops.feed_validation.validate_catalog()
    bad = [f for f in feeds if f.reliability < 0.2 and f.error]
    if len(bad) == len(feeds) and feeds:
        failures.append("all feeds failed fetch")

    counts = ops.storage.snapshot_tables()
    if not counts:
        failures.append("storage snapshot empty")

    readiness = ops.repository.latest_readiness_score()
    burnin = ops.repository.active_burnin()
    report_path = Path("var/reports/staging_verification.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    status = "READY" if not failures else "NOT READY"
    body = [
        f"# Staging verification — {datetime.now(timezone.utc).isoformat()}",
        "",
        f"**Status:** {status}",
        "",
        "## Smoke checks",
        *lines,
        "",
        f"Feeds checked: {len(feeds)}",
        f"Tables tracked: {len(counts)}",
        f"Active burn-in: {burnin['run_id'] if burnin else 'none'}",
        f"Readiness score: {readiness['staging_score'] if readiness else 'n/a'}",
    ]
    if failures:
        body.extend(["", "## Failures", *[f"- {f}" for f in failures]])
    report_path.write_text("\n".join(body), encoding="utf-8")

    if failures:
        print("STAGING NOT READY:")
        for f in failures:
            print(f"  - {f}")
        print(f"Report: {report_path}")
        return 1
    print("STAGING READY")
    print(f"  feeds checked: {len(feeds)}")
    print(f"  tables tracked: {len(counts)}")
    print(f"Report: {report_path}")
    return 0
