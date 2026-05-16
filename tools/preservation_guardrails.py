#!/usr/bin/env python3
"""Read-only preservation / long-horizon survivability guardrails."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PRESERVATION_DOCS = (
    "docs/preservation/ecosystem_aging.md",
    "docs/preservation/dependency_preservation.md",
    "docs/preservation/long_horizon_recovery.md",
    "docs/preservation/minimal_survivable_profile.md",
    "docs/preservation/operational_durability.md",
    "docs/preservation/preservation_governance.md",
    "docs/v2x_preservation_readiness_report.md",
)

STEWARDSHIP_LINKS = (
    "docs/stewardship/adr_lineage_map.md",
    "docs/stewardship/ecosystem_continuity.md",
    "docs/stewardship/release_archaeology.md",
)

CRITICAL_RUNTIME_DEPS = (
    "telethon",
    "aiogram",
    "openai",
    "sqlalchemy",
    "aiosqlite",
    "APScheduler",
)


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def check_preservation_docs(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("HIGH", "missing_preservation_doc", f"Missing {rel}", "Add preservation documentation")
        for rel in PRESERVATION_DOCS
        if not (repo / rel).is_file()
    ]


def check_stewardship_linkage(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("MEDIUM", "missing_stewardship_link", f"Missing {rel}", "Restore traceability doc")
        for rel in STEWARDSHIP_LINKS
        if not (repo / rel).is_file()
    ]


def check_python_floor(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return [_hint("HIGH", "pyproject_missing", "pyproject.toml missing", "Restore packaging metadata")]
    text = pyproject.read_text(encoding="utf-8")
    m = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', text)
    if not m:
        findings.append(
            _hint("HIGH", "python_floor_missing", "requires-python not set", "Document Python floor"),
        )
    else:
        floor = m.group(1)
        if "3.12" not in floor and "3.13" not in floor and "3.14" not in floor:
            findings.append(
                _hint(
                    "MEDIUM",
                    "python_floor_stale",
                    f"requires-python={floor} — review EOL",
                    "Update ecosystem_aging.md + pins",
                ),
            )
    return findings


def check_dependency_pins(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    req = repo / "requirements.txt"
    if not req.is_file():
        return [_hint("HIGH", "requirements_missing", "requirements.txt missing", "Restore pins")]
    lines = req.read_text(encoding="utf-8").splitlines()
    unpinned_critical = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        name = s.split("==")[0].split("[")[0].strip().lower()
        for crit in CRITICAL_RUNTIME_DEPS:
            if name == crit.lower() and "==" not in s and ">=" not in s:
                unpinned_critical.append(s)
    if unpinned_critical:
        findings.append(
            _hint(
                "MEDIUM",
                "unpinned_critical_dep",
                f"Loosely pinned: {unpinned_critical[:3]}",
                "Pin critical deps per dependency_preservation.md",
            ),
        )
    floating = [ln for ln in lines if ln.strip().startswith(("redis>=", "asyncpg>=", "psycopg"))]
    if len(floating) > 2:
        findings.append(
            _hint(
                "LOW",
                "floating_optional_ranges",
                "Multiple >= pins on optional deps — review on uplift",
                "Document in dependency_preservation.md",
            ),
        )
    return findings


def check_frozen_contracts() -> list[dict[str, str]]:
    try:
        from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION

        if FROZEN_SCHEMA_VERSION != 1 or len(FROZEN_ARTIFACT_FILENAMES) != 14:
            return [
                _hint(
                    "HIGH",
                    "frozen_contract_drift",
                    "Runtime contract changed",
                    "Preservation phase must not alter contracts",
                ),
            ]
    except Exception as exc:
        return [_hint("HIGH", "contract_import_failed", str(exc), "Fix runtime_contracts")]
    return []


def check_recovery_coverage(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    lhr = repo / "docs/preservation/long_horizon_recovery.md"
    if lhr.is_file():
        text = lhr.read_text(encoding="utf-8").lower()
        for phrase in ("5 years", "maintainer gap", "archival backup"):
            if phrase not in text:
                findings.append(
                    _hint("MEDIUM", "recovery_scenario_gap", f"Missing scenario: {phrase}", "Update long_horizon_recovery.md"),
                )
    return findings


def check_deprecated_tooling_accumulation(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    tools = list((repo / "tools").glob("*.py")) if (repo / "tools").is_dir() else []
    if len(tools) > 40:
        findings.append(
            _hint(
                "LOW",
                "tool_proliferation",
                f"{len(tools)} tools/*.py — preserve discoverability via docs-map",
                "Avoid duplicate guardrails",
            ),
        )
    return findings


def check_ecosystem_survivability_warnings(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    aging = repo / "docs/preservation/ecosystem_aging.md"
    if aging.is_file():
        text = aging.read_text(encoding="utf-8")
        for ext in ("Telethon", "OpenAI", "Python"):
            if ext not in text:
                findings.append(
                    _hint("LOW", "aging_doc_gap", f"{ext} not in ecosystem_aging.md", "Document outlook"),
                )
    return findings


def run_guardrails(*, repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    findings: list[dict[str, str]] = []
    findings.extend(check_preservation_docs(root))
    findings.extend(check_stewardship_linkage(root))
    findings.extend(check_python_floor(root))
    findings.extend(check_dependency_pins(root))
    findings.extend(check_frozen_contracts())
    findings.extend(check_recovery_coverage(root))
    findings.extend(check_deprecated_tooling_accumulation(root))
    findings.extend(check_ecosystem_survivability_warnings(root))

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
        "preservation_index": "docs/preservation/preservation_governance.md",
        "note": "Survivability hints — not archival certification",
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
