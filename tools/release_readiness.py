#!/usr/bin/env python3
"""Read-only release readiness validator (governance gate)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

GOVERNANCE_DOCS = (
    "docs/compatibility_policy.md",
    "docs/deprecation_policy.md",
    "docs/release_governance.md",
    "docs/migration_safety.md",
    "docs/evidence_lifecycle.md",
    "docs/feature_flag_governance.md",
    "docs/maintenance_matrix.md",
    "docs/v1_4_release_governance_report.md",
)

UPGRADE_RUNBOOKS = (
    "docs/runbooks/upgrades/PATCH_UPGRADE.md",
    "docs/runbooks/upgrades/MINOR_UPGRADE.md",
    "docs/runbooks/upgrades/SAFE_ROLLBACK.md",
    "docs/runbooks/upgrades/EXPERIMENTAL_FLAG_ENABLE.md",
    "docs/runbooks/upgrades/SQLITE_MIGRATION_PRECHECK.md",
)

# Registry SSOT for readiness checks (must match docs/feature_flag_governance.md)
OPT_IN_FLAGS: dict[str, dict[str, str]] = {
    "WORKER_RETRY_SAFE": {"since": "v1.1", "class": "reliability"},
    "PUBLISH_LOCK_STRICT": {"since": "v1.1", "class": "reliability"},
    "RUNTIME_DRIFT_MONITOR": {"since": "v1.3", "class": "diagnostic"},
    "SCHEDULER_DIAGNOSTICS": {"since": "v1.3", "class": "diagnostic"},
    "SECURITY_REDACTION": {"since": "v1.6", "class": "reliability"},
}

INCOMPATIBLE_ENV: tuple[tuple[dict[str, str], str], ...] = (
    (
        {"PUBLISH_LOCK_STRICT": "1", "REDIS_ENABLED": "0"},
        "PUBLISH_LOCK_STRICT with REDIS_ENABLED=0 blocks multi-worker publish paths",
    ),
)


def _check_docs(repo: Path, paths: tuple[str, ...], label: str) -> list[str]:
    errors: list[str] = []
    for rel in paths:
        if not (repo / rel).is_file():
            errors.append(f"{label}: missing {rel}")
    return errors


def check_runtime_contracts() -> list[str]:
    from observability.runtime_contracts import (
        FROZEN_ARTIFACT_FILENAMES,
        FROZEN_LIFECYCLE_ORDER,
        FROZEN_SCHEMA_VERSION,
        INSPECTION_CLI_COMMANDS,
    )

    errors: list[str] = []
    if len(FROZEN_ARTIFACT_FILENAMES) != 14:
        errors.append(f"contract: expected 14 artifacts, got {len(FROZEN_ARTIFACT_FILENAMES)}")
    if len(INSPECTION_CLI_COMMANDS) != 11:
        errors.append(f"contract: expected 11 CLIs, got {len(INSPECTION_CLI_COMMANDS)}")
    if FROZEN_SCHEMA_VERSION != 1:
        errors.append(f"contract: schema version must be 1, got {FROZEN_SCHEMA_VERSION}")
    if list(FROZEN_LIFECYCLE_ORDER) != list(range(1, 15)):
        errors.append("contract: lifecycle order must be 1..14")
    return errors


def check_feature_flag_registry() -> list[str]:
    errors: list[str] = []
    text = (REPO / "docs/feature_flag_governance.md").read_text(encoding="utf-8")
    for name in OPT_IN_FLAGS:
        if name not in text:
            errors.append(f"flag {name} not documented in feature_flag_governance.md")
    return errors


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def check_env_combinations() -> list[str]:
    warnings: list[str] = []
    if _env_truthy("PUBLISH_LOCK_STRICT") and not _env_truthy("REDIS_ENABLED"):
        warnings.append(
            "env: PUBLISH_LOCK_STRICT=1 with REDIS_ENABLED=0 — single-worker only; see feature_flag_governance.md"
        )
    return warnings


def check_evidence_compatibility(output_dir: Path | None) -> list[str]:
    if output_dir is None or not output_dir.is_dir():
        return []
    from observability.runtime_contracts import REQUIRED_ARTIFACT_FILENAMES

    errors: list[str] = []
    rt = output_dir / "runtime"
    if not rt.is_dir():
        return [f"evidence: no runtime/ under {output_dir}"]
    for name in REQUIRED_ARTIFACT_FILENAMES:
        if name == "runtime_index.json":
            continue
        if not (rt / name).is_file():
            errors.append(f"evidence: missing required {name}")
    return errors


def run_pytest_subset(strict: bool) -> list[str]:
    errors: list[str] = []
    tests = [
        "tests/contracts/test_runtime_contracts.py",
        "tests/contracts/test_v1_4_governance_docs.py",
    ]
    if strict:
        tests.append("tests/contracts/test_packaging_consistency.py")
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "--tb=line"]
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.returncode != 0:
        errors.append(f"pytest failed: {proc.stdout[-800:]}{proc.stderr[-400:]}")
    return errors


def build_report(results: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "read_only": True,
        "status": results["status"],
        "errors": results["errors"],
        "warnings": results["warnings"],
        "checks": results["checks"],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Release readiness (read-only)")
    p.add_argument("--strict", action="store_true", help="Include extra contract tests")
    p.add_argument("--check-env", action="store_true", help="Warn on incompatible env combos")
    p.add_argument("--output-dir", default="", help="Optional OUTPUT_DIR evidence check")
    p.add_argument("--json-output", default="", help="Write JSON report path")
    p.add_argument("--skip-pytest", action="store_true")
    args = p.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, str] = {}

    errors.extend(_check_docs(REPO, GOVERNANCE_DOCS, "governance"))
    errors.extend(_check_docs(REPO, UPGRADE_RUNBOOKS, "upgrade"))
    checks["governance_docs"] = "OK" if not errors else "FAIL"

    ce = check_runtime_contracts()
    errors.extend(ce)
    checks["runtime_contracts"] = "OK" if not ce else "FAIL"

    fe = check_feature_flag_registry()
    errors.extend(fe)
    checks["feature_flags"] = "OK" if not fe else "FAIL"

    if args.check_env:
        warnings.extend(check_env_combinations())
        checks["env_combinations"] = "OK" if not warnings else "WARNING"

    od = Path(args.output_dir).expanduser() if args.output_dir else None
    ee = check_evidence_compatibility(od)
    errors.extend(ee)
    checks["evidence"] = "OK" if not ee else ("SKIP" if od is None else "FAIL")

    if not args.skip_pytest:
        pe = run_pytest_subset(args.strict)
        errors.extend(pe)
        checks["contract_tests"] = "OK" if not pe else "FAIL"

    status = "FAIL" if errors else ("WARNING" if warnings else "OK")
    report = build_report(
        {"status": status, "errors": errors, "warnings": warnings, "checks": checks}
    )

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))

    if status == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
