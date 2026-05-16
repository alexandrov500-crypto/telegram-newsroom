#!/usr/bin/env python3
"""Read-only legacy stewardship / controlled sunset guardrails."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LEGACY_DOCS = (
    "docs/legacy/legacy_state_definition.md",
    "docs/legacy/controlled_sunset.md",
    "docs/legacy/recoverability_guarantees.md",
    "docs/legacy/legacy_operational_envelope.md",
    "docs/legacy/stewardship_sunset_governance.md",
    "docs/legacy/legacy_antipatterns.md",
    "docs/v2x_legacy_stewardship_report.md",
)

UPSTREAM_DOCS = (
    "docs/preservation/preservation_governance.md",
    "docs/stewardship/ecosystem_continuity.md",
    "docs/architecture/v2_transition_strategy.md",
    "docs/MAINTENANCE_MODE.md",
)

GUARDRAIL_TOOLS = (
    "preservation_guardrails.py",
    "history_guardrails.py",
    "architecture_guardrails.py",
    "semantics_guardrails.py",
    "scalability_diagnostics.py",
)


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def check_legacy_docs(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("HIGH", "missing_legacy_doc", f"Missing {rel}", "Add legacy stewardship doc")
        for rel in LEGACY_DOCS
        if not (repo / rel).is_file()
    ]


def check_upstream_linkage(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("MEDIUM", "missing_upstream_doc", f"Missing {rel}", "Restore preservation/stewardship doc")
        for rel in UPSTREAM_DOCS
        if not (repo / rel).is_file()
    ]


def check_preservation_compatibility(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    recover = repo / "docs/legacy/recoverability_guarantees.md"
    preservation = repo / "docs/preservation/long_horizon_recovery.md"
    if recover.is_file() and preservation.is_file():
        rt = recover.read_text(encoding="utf-8").lower()
        if "tag" not in rt and "archive" not in rt:
            findings.append(
                _hint("MEDIUM", "recoverability_gap", "Legacy recoverability missing tag/archive", "Align with preservation"),
            )
    return findings


def check_governance_sprawl(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    makefile = repo / "Makefile"
    if makefile.is_file():
        targets = makefile.read_text(encoding="utf-8").count(":")
        if targets > 75:
            findings.append(
                _hint(
                    "LOW",
                    "stewardship_surface_growth",
                    f"~{targets} Makefile lines with targets — review scale-down",
                    "See stewardship_sunset_governance.md",
                ),
            )
    tools = list((repo / "tools").glob("*guardrails*.py"))
    if len(tools) > 6:
        findings.append(
            _hint(
                "LOW",
                "guardrails_proliferation",
                f"{len(tools)} guardrails tools — avoid new ones in passive mode",
                "Merge hints into existing tools",
            ),
        )
    return findings


def check_modernization_pressure_docs(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    antipatterns = repo / "docs/legacy/legacy_antipatterns.md"
    if antipatterns.is_file():
        text = antipatterns.read_text(encoding="utf-8").lower()
        for phrase in ("panic modernization", "rewrite-before-sunset", "perpetual evolution"):
            if phrase not in text:
                findings.append(
                    _hint("LOW", "antipattern_gap", f"Missing anti-pattern: {phrase}", "Update legacy_antipatterns.md"),
                )
    return findings


def check_dormant_consistency(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    sunset = repo / "docs/legacy/controlled_sunset.md"
    continuity = repo / "docs/stewardship/ecosystem_continuity.md"
    if sunset.is_file() and continuity.is_file():
        st = sunset.read_text(encoding="utf-8").lower()
        if "dormant" not in st and "years" not in st:
            findings.append(
                _hint("MEDIUM", "sunset_dormant_gap", "controlled_sunset missing dormancy scenarios", "Document no-release years"),
            )
    return findings


def check_frozen_contracts() -> list[dict[str, str]]:
    try:
        from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION

        if FROZEN_SCHEMA_VERSION != 1 or len(FROZEN_ARTIFACT_FILENAMES) != 14:
            return [
                _hint("HIGH", "contract_drift", "Runtime contract drift", "Legacy phase must not change contracts"),
            ]
    except Exception as exc:
        return [_hint("HIGH", "contract_check_failed", str(exc), "Fix runtime_contracts")]
    return []


def run_guardrails(*, repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    findings: list[dict[str, str]] = []
    findings.extend(check_legacy_docs(root))
    findings.extend(check_upstream_linkage(root))
    findings.extend(check_preservation_compatibility(root))
    findings.extend(check_governance_sprawl(root))
    findings.extend(check_modernization_pressure_docs(root))
    findings.extend(check_dormant_consistency(root))
    findings.extend(check_frozen_contracts())

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
        "legacy_index": "docs/legacy/stewardship_sunset_governance.md",
        "note": "Legacy stewardship hints — not shutdown automation",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    report = run_guardrails()
    if args.strict:
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
