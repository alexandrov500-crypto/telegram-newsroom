#!/usr/bin/env python3
"""Read-only historical traceability / stewardship guardrails."""

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

STEWARDSHIP_DOCS = (
    "docs/stewardship/adr_lineage_map.md",
    "docs/stewardship/release_archaeology.md",
    "docs/stewardship/operational_history.md",
    "docs/stewardship/ecosystem_continuity.md",
    "docs/stewardship/decision_archaeology_index.md",
    "docs/stewardship/long_term_readability.md",
    "docs/v2x_historical_traceability_report.md",
)

PHASE_REPORTS = (
    "docs/v1_1_operational_validation_report.md",
    "docs/v1_3_resilience_validation_report.md",
    "docs/v1_4_release_governance_report.md",
    "docs/v1_6_security_hardening_report.md",
    "docs/v1_8_scalability_boundaries_report.md",
    "docs/v1_9_operational_intelligence_report.md",
    "docs/v2_transition_strategy_report.md",
    "docs/v2x_operational_semantics_report.md",
)

ADR_INDEX = REPO / "docs/architecture/README.md"
ADR_DIR = REPO / "docs/architecture"
RFC_DIR = REPO / "docs/rfc"

CHRONOLOGY_MARKERS = (
    "v1.0",
    "v1.1",
    "v1.3",
    "v1.4",
    "v1.6",
    "v1.8",
    "v1.9",
    "v2.x",
)


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def check_stewardship_docs(repo: Path) -> list[dict[str, str]]:
    return [
        _hint("HIGH", "missing_stewardship_doc", f"Missing {rel}", "Add stewardship documentation")
        for rel in STEWARDSHIP_DOCS
        if not (repo / rel).is_file()
    ]


def check_adr_index_coverage(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    index_path = repo / "docs/architecture/README.md"
    if not index_path.is_file():
        return [_hint("HIGH", "adr_index_missing", "ADR index missing", "Restore architecture/README.md")]
    text = index_path.read_text(encoding="utf-8")
    for adr in sorted(ADR_DIR.glob("ADR-0*.md")):
        if adr.name.startswith("ADR-") and adr.name not in text:
            findings.append(
                _hint("MEDIUM", "adr_orphan", f"{adr.name} not in ADR index", "Update architecture/README.md"),
            )
    lineage = repo / "docs/stewardship/adr_lineage_map.md"
    if lineage.is_file():
        lt = lineage.read_text(encoding="utf-8")
        for anchor in ("015", "017", "024", "025", "026"):
            if anchor not in lt:
                findings.append(
                    _hint(
                        "LOW",
                        "lineage_anchor_gap",
                        f"{anchor} not in adr_lineage_map.md",
                        "Add anchor to lineage map",
                    ),
                )
    return findings[:15]


def check_rfc_orphans(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    readme = RFC_DIR / "README.md"
    if not readme.is_file():
        return [_hint("MEDIUM", "rfc_readme_missing", "docs/rfc/README.md missing", "Restore RFC index")]
    text = readme.read_text(encoding="utf-8")
    for rfc in sorted(RFC_DIR.glob("RFC-*.md")):
        if rfc.name not in text:
            findings.append(
                _hint("LOW", "rfc_orphan", f"{rfc.name} not in rfc/README.md", "Index RFC in README"),
            )
    archaeology = repo / "docs/stewardship/decision_archaeology_index.md"
    if archaeology.is_file() and "RFC-010" not in archaeology.read_text(encoding="utf-8"):
        findings.append(
            _hint("LOW", "archaeology_rfc_gap", "RFC-010 not in decision_archaeology_index", "Update index"),
        )
    return findings


def check_release_chronology(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    arch = repo / "docs/stewardship/release_archaeology.md"
    if not arch.is_file():
        return findings
    text = arch.read_text(encoding="utf-8")
    for marker in ("v1.0 freeze", "v1.1", "semantics formalization"):
        if marker.lower() not in text.lower():
            findings.append(
                _hint("MEDIUM", "chronology_gap", f"release_archaeology missing '{marker}'", "Document phase"),
            )
    for rel in PHASE_REPORTS:
        if not (repo / rel).is_file():
            findings.append(_hint("MEDIUM", "missing_phase_report", f"Missing {rel}", "Restore or update index"))
    return findings


def check_stale_release_refs(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    changelog = repo / "CHANGELOG.md"
    if changelog.is_file() and "v1.0.0" not in changelog.read_text(encoding="utf-8"):
        findings.append(
            _hint("LOW", "changelog_v1_ref", "CHANGELOG missing v1.0.0 reference", "Preserve freeze note"),
        )
    start = repo / "docs/START_HERE.md"
    if start.is_file() and "START_HERE" in start.name:
        st = start.read_text(encoding="utf-8")
        if "stewardship" not in st.lower() and "traceability" not in st.lower():
            findings.append(
                _hint("LOW", "start_here_stewardship", "START_HERE missing stewardship link", "Add traceability bullet"),
            )
    return findings


def check_broken_stewardship_links(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    link_re = re.compile(r"\]\(([^)]+)\)")
    for rel in STEWARDSHIP_DOCS:
        path = repo / rel
        if not path.is_file():
            continue
        for match in link_re.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1).split("#")[0]
            if not target or target.startswith("http"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                findings.append(
                    _hint(
                        "MEDIUM",
                        "broken_stewardship_link",
                        f"{rel} → {target}",
                        "Fix relative link",
                    ),
                )
    return findings[:10]


def check_terminology_duplicates(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    policies = [
        "compatibility_policy.md",
        "release_governance.md",
        "feature_flag_governance.md",
    ]
    missing = [p for p in policies if not (repo / "docs" / p).is_file()]
    if missing:
        findings.append(
            _hint("MEDIUM", "governance_ssot_gap", f"Missing SSOT: {missing}", "Restore governance docs"),
        )
    return findings


def check_runtime_unchanged() -> list[dict[str, str]]:
    try:
        from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION

        if FROZEN_SCHEMA_VERSION != 1 or len(FROZEN_ARTIFACT_FILENAMES) != 14:
            return [
                _hint(
                    "HIGH",
                    "contract_drift",
                    "Runtime contract changed — traceability phase must not alter contracts",
                    "Revert or v2 program",
                ),
            ]
    except Exception as exc:
        return [_hint("HIGH", "contract_check_failed", str(exc), "Fix imports")]
    return []


def run_guardrails(*, repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    findings: list[dict[str, str]] = []
    findings.extend(check_stewardship_docs(root))
    findings.extend(check_adr_index_coverage(root))
    findings.extend(check_rfc_orphans(root))
    findings.extend(check_release_chronology(root))
    findings.extend(check_stale_release_refs(root))
    findings.extend(check_broken_stewardship_links(root))
    findings.extend(check_terminology_duplicates(root))
    findings.extend(check_runtime_unchanged())

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
        "stewardship_index": "docs/stewardship/decision_archaeology_index.md",
        "note": "Historical traceability hints — not compliance certification",
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
