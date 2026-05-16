#!/usr/bin/env python3
"""Read-only operational semantics / invariant guardrails."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SEMANTICS_DOCS = (
    "docs/semantics/operational_invariants.md",
    "docs/semantics/forbidden_states.md",
    "docs/semantics/recovery_semantics.md",
    "docs/semantics/consistency_matrix.md",
    "docs/semantics/assumption_audit.md",
    "docs/semantics/semantics_governance.md",
    "docs/v2x_operational_semantics_report.md",
)

FORBIDDEN_ENV: tuple[tuple[dict[str, str], str, str], ...] = (
    (
        {"REDIS_ENABLED": "1", "PUBLISH_LOCK_STRICT": "0"},
        "forbidden_multi_worker_lock",
        "Multi-worker Redis without PUBLISH_LOCK_STRICT — see forbidden_states.md",
    ),
    (
        {"PUBLISH_LOCK_STRICT": "1", "REDIS_ENABLED": "0"},
        "forbidden_strict_without_redis",
        "PUBLISH_LOCK_STRICT without REDIS_ENABLED — publish fail-closed",
    ),
    (
        {"REDIS_ENABLED": "1", "WORKER_RETRY_SAFE": "0"},
        "unsafe_retry_semantics",
        "REDIS_ENABLED with WORKER_RETRY_SAFE=0 — legacy ack-before-enqueue on retry",
    ),
)


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def check_semantics_docs(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("HIGH", "missing_semantics_doc", f"Missing {rel}", "Add semantics documentation")
        for rel in SEMANTICS_DOCS
        if not (repo / rel).is_file()
    ]


def check_forbidden_env() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for combo, code, msg in FORBIDDEN_ENV:
        if all(_env_on(k) == (v == "1") for k, v in combo.items()):
            findings.append(_hint("HIGH", code, msg, "Fix .env or reduce workers; see semantics_guardrails"))
    return findings


def check_runtime_contracts() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION

        if FROZEN_SCHEMA_VERSION != 1:
            findings.append(
                _hint("HIGH", "schema_drift", f"schema version {FROZEN_SCHEMA_VERSION}", "Major version required"),
            )
        if len(FROZEN_ARTIFACT_FILENAMES) != 14:
            findings.append(
                _hint("HIGH", "artifact_drift", f"{len(FROZEN_ARTIFACT_FILENAMES)} artifacts", "Contract freeze"),
            )
    except Exception as exc:
        findings.append(_hint("HIGH", "contract_check_failed", str(exc), "Fix runtime_contracts"))
    return findings


def check_recovery_assumptions(output_dir: Path | None) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if output_dir and output_dir.is_dir():
        from utils.recovery_intelligence import build_recovery_assessment

        ass = build_recovery_assessment(output_dir)
        for w in ass.get("degraded_recovery_warnings") or []:
            findings.append(_hint("MEDIUM", "recovery_degraded", w, "validate-recovery before promote"))
        for p in ass.get("unsafe_patterns") or []:
            findings.append(
                _hint(
                    str(p.get("severity", "MEDIUM")),
                    str(p.get("code", "unsafe_recovery")),
                    str(p.get("message", "")),
                    "Quiesce before restore",
                ),
            )
    return findings


def check_retention_invariants(output_dir: Path | None) -> list[dict[str, str]]:
    if not output_dir or not output_dir.is_dir():
        return []
    rt = output_dir / "runtime"
    required = (
        "health_snapshot.json",
        "runtime_manifest.json",
        "runtime_report.json",
    )
    findings: list[dict[str, str]] = []
    present = sum(1 for n in required if (rt / n).is_file())
    if 0 < present < len(required):
        findings.append(
            _hint(
                "HIGH",
                "partial_recovery_state",
                f"Partial runtime/ artifacts ({present}/{len(required)} core files)",
                "Re-run runtime-nightly or restore full tree",
            ),
        )
    return findings


def check_invariant_doc_coverage(repo: Path) -> list[dict[str, str]]:
    inv = repo / "docs/semantics/operational_invariants.md"
    if not inv.is_file():
        return []
    text = inv.read_text(encoding="utf-8")
    required_topics = ("Queue delivery", "Retry semantics", "Publish lock", "WAL maintenance")
    missing = [t for t in required_topics if t not in text]
    if missing:
        return [
            _hint("MEDIUM", "invariant_doc_gap", f"Missing topics: {missing}", "Update operational_invariants.md"),
        ]
    return []


def run_guardrails(*, repo: Path | None = None, output_dir: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    od = output_dir or (
        Path(os.environ["OUTPUT_DIR"]) if os.environ.get("OUTPUT_DIR") else None
    )
    findings: list[dict[str, str]] = []
    findings.extend(check_semantics_docs(root))
    findings.extend(check_forbidden_env())
    findings.extend(check_runtime_contracts())
    findings.extend(check_recovery_assumptions(od))
    findings.extend(check_retention_invariants(od))
    findings.extend(check_invariant_doc_coverage(root))

    order = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
    worst = max((order.get(f["severity"], 0) for f in findings), default=0)
    status = "FAIL" if worst >= 3 else ("WARNING" if findings else "OK")

    return {
        "schema_version": 1,
        "read_only": True,
        "advisory_only": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "finding_count": len(findings),
        "findings": findings,
        "invariant_registry": "docs/semantics/operational_invariants.md",
        "note": "Verification hints — not a formal proof",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default=os.environ.get("OUTPUT_DIR", ""))
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    od = Path(args.output_dir) if args.output_dir else None
    report = run_guardrails(output_dir=od)
    if args.strict and report.get("findings"):
        highs = [f for f in report["findings"] if f.get("severity") == "HIGH"]
        if highs:
            report["status"] = "FAIL"
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
