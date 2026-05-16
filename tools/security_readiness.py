#!/usr/bin/env python3
"""Security readiness gate (read-only)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SECURITY_DOCS = (
    "docs/security/secrets_hygiene.md",
    "docs/security/supply_chain_integrity.md",
    "docs/security/artifact_integrity.md",
    "docs/security/auditability.md",
    "docs/security/trust_boundaries.md",
    "docs/v1_6_security_hardening_report.md",
)

SECURITY_RUNBOOKS = (
    "docs/runbooks/security/TOKEN_ROTATION.md",
    "docs/runbooks/security/REDACTION_FAILURE.md",
    "docs/runbooks/security/SUSPECTED_SECRET_LEAK.md",
    "docs/runbooks/security/COMPROMISED_RUNTIME.md",
    "docs/runbooks/security/EVIDENCE_TAMPERING.md",
    "docs/runbooks/security/UNSAFE_CONFIGURATION.md",
    "docs/runbooks/security/INCIDENT_CONTAINMENT.md",
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    p.add_argument("--json-output", default="")
    p.add_argument("--skip-tools", action="store_true")
    args = p.parse_args()

    errors: list[str] = []
    checks: dict[str, str] = {}

    for rel in SECURITY_DOCS + SECURITY_RUNBOOKS:
        if not (REPO / rel).is_file():
            errors.append(f"missing {rel}")
    checks["security_docs"] = "OK" if not errors else "FAIL"

    if not (REPO / "utils/security_redaction.py").is_file():
        errors.append("missing utils/security_redaction.py")
    checks["redaction_module"] = (
        "OK" if (REPO / "utils/security_redaction.py").is_file() else "FAIL"
    )

    text = (REPO / "docs/feature_flag_governance.md").read_text(encoding="utf-8")
    if "SECURITY_REDACTION" not in text:
        errors.append("SECURITY_REDACTION not in feature_flag_governance.md")
    checks["feature_flag_doc"] = "OK" if "SECURITY_REDACTION" in text else "FAIL"

    if not args.skip_tools:
        for label, cmd in (
            ("dependency_audit", [sys.executable, str(REPO / "tools/dependency_audit.py")]),
            ("posture_check", [sys.executable, str(REPO / "tools/security_posture_check.py")]),
        ):
            proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
            if proc.returncode != 0:
                errors.append(f"{label} failed")
            checks[label] = "OK" if proc.returncode == 0 else "FAIL"

        if args.strict:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/test_security_redaction.py", "-q"],
                cwd=str(REPO),
                capture_output=True,
                text=True,
            )
            checks["redaction_tests"] = "OK" if proc.returncode == 0 else "FAIL"
            if proc.returncode != 0:
                errors.append("redaction tests failed")

    status = "FAIL" if errors else "OK"
    report = {
        "schema_version": 1,
        "read_only": True,
        "status": status,
        "errors": errors,
        "checks": checks,
    }
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
