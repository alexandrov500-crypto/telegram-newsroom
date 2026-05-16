#!/usr/bin/env python3
"""Unsafe configuration detection (read-only)."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _finding(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def run_checks(*, output_dir: Path | None) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if _env_truthy("PUBLISH_LOCK_STRICT") and not _env_truthy("REDIS_ENABLED"):
        findings.append(
            _finding(
                "HIGH",
                "strict_lock_without_redis",
                "PUBLISH_LOCK_STRICT=1 with REDIS_ENABLED=0",
                "Use single publisher or enable Redis for multi-worker",
            )
        )
    if not _env_truthy("WORKER_RETRY_SAFE") and _env_truthy("REDIS_ENABLED"):
        findings.append(
            _finding(
                "MEDIUM",
                "legacy_retry_with_redis",
                "WORKER_RETRY_SAFE=0 under Redis queue",
                "Set WORKER_RETRY_SAFE=1 for safer retry ordering",
            )
        )
    if _env_truthy("REDIS_ENABLED") and not _env_truthy("PUBLISH_LOCK_STRICT"):
        findings.append(
            _finding(
                "MEDIUM",
                "redis_without_strict_lock",
                "Multi-worker risk: Redis on but PUBLISH_LOCK_STRICT off",
                "Enable PUBLISH_LOCK_STRICT=1 when multiple publishers",
            )
        )
    if os.environ.get("LOG_LEVEL", "").strip().upper() == "DEBUG":
        findings.append(
            _finding(
                "LOW",
                "debug_log_level",
                "LOG_LEVEL=DEBUG may increase sensitive data in logs",
                "Use INFO in production; enable SECURITY_REDACTION=1",
            )
        )
    if not _env_truthy("SECURITY_REDACTION"):
        findings.append(
            _finding(
                "LOW",
                "redaction_disabled",
                "SECURITY_REDACTION is off",
                "Enable SECURITY_REDACTION=1 for production log hygiene",
            )
        )

    if output_dir is not None:
        od = output_dir.expanduser().resolve()
        if od.is_dir():
            mode = stat.S_IMODE(od.stat().st_mode)
            if mode & stat.S_IWOTH:
                findings.append(
                    _finding(
                        "HIGH",
                        "world_writable_output_dir",
                        f"OUTPUT_DIR world-writable: {od}",
                        "chmod o-w on inspection directory",
                    )
                )

    return findings


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="")
    p.add_argument("--json-output", default="")
    p.add_argument("--fail-on", default="HIGH", help="Minimum severity to fail: LOW|MEDIUM|HIGH")
    args = p.parse_args()

    od = Path(args.output_dir) if args.output_dir else None
    findings = run_checks(output_dir=od)
    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    threshold = order.get(args.fail_on.upper(), 3)
    worst = max((order.get(f["severity"], 0) for f in findings), default=0)
    status = "FAIL" if worst >= threshold and findings else "OK"

    report = {"status": status, "finding_count": len(findings), "findings": findings}
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
