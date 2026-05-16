#!/usr/bin/env python3
"""Read-only architecture / stewardship guardrails (v2 transition strategy)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

V2_STRATEGY_DOCS = (
    "docs/architecture/architectural_preservation.md",
    "docs/architecture/v2_transition_strategy.md",
    "docs/architecture/technical_debt_governance.md",
    "docs/architecture/complexity_budget.md",
    "docs/architecture/evolution_decision_matrix.md",
    "docs/architecture/future_scalability_realities.md",
    "docs/architecture/maintainer_longevity.md",
    "docs/architecture/operational_philosophy.md",
    "docs/v2_transition_strategy_report.md",
)

ADR_INDEX = "docs/architecture/README.md"
ADR_DIR = REPO / "docs/architecture"

CREEP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bkubernetes\b|\bk8s\b", "kubernetes_reference"),
    (r"\bmicroservice", "microservice_split"),
    (r"\bmandatory\s+postgres", "mandatory_postgres"),
    (r"\bevent[- ]?bus\b|\bkafka\b|\bnats\b", "event_platform"),
    (r"\bself[- ]?heal", "autonomous_healing"),
    (r"\bautoscaling\b", "autoscaling_platform"),
)

UNSUPPORTED_ENV: tuple[tuple[dict[str, str], str], ...] = (
    (
        {"REDIS_ENABLED": "1", "PUBLISH_LOCK_STRICT": "0"},
        "Multi-worker Redis without PUBLISH_LOCK_STRICT",
    ),
)


def _hint(severity: str, code: str, message: str, remediation: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message, "remediation": remediation}


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def check_strategy_docs(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for rel in V2_STRATEGY_DOCS:
        if not (repo / rel).is_file():
            findings.append(
                _hint("HIGH", "missing_strategy_doc", f"Missing {rel}", "Add v2 stewardship documentation"),
            )
    return findings


def check_adr_linkage(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    index_path = repo / ADR_INDEX
    if not index_path.is_file():
        return [_hint("HIGH", "adr_index_missing", "ADR index missing", f"Restore {ADR_INDEX}")]
    index_text = index_path.read_text(encoding="utf-8")
    adrs = sorted(ADR_DIR.glob("ADR-*.md"))
    for adr in adrs:
        if adr.name not in index_text and adr.name != "POST_V1_ADR_BACKLOG.md":
            findings.append(
                _hint(
                    "MEDIUM",
                    "adr_not_indexed",
                    f"{adr.name} not linked in ADR index",
                    "Add row to docs/architecture/README.md",
                ),
            )
    if "ADR-024" not in index_text and (ADR_DIR / "ADR-024-v2-transition-strategy.md").is_file():
        findings.append(
            _hint("MEDIUM", "adr_024_index", "ADR-024 not in index", "Update ADR index table"),
        )
    return findings


def check_governance_consistency(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION

        if FROZEN_SCHEMA_VERSION != 1:
            findings.append(
                _hint(
                    "HIGH",
                    "schema_version_drift",
                    f"FROZEN_SCHEMA_VERSION={FROZEN_SCHEMA_VERSION} (expected 1 for 1.x)",
                    "v2 program required for schema bump",
                ),
            )
        if len(FROZEN_ARTIFACT_FILENAMES) != 14:
            findings.append(
                _hint(
                    "HIGH",
                    "artifact_count_drift",
                    f"Expected 14 frozen artifacts, got {len(FROZEN_ARTIFACT_FILENAMES)}",
                    "ADR + v2 gate for contract change",
                ),
            )
    except Exception as exc:
        findings.append(
            _hint("HIGH", "contract_import_failed", str(exc), "Fix runtime_contracts module"),
        )

    flag_doc = repo / "docs/feature_flag_governance.md"
    if flag_doc.is_file():
        text = flag_doc.read_text(encoding="utf-8")
        for flag in ("WORKER_RETRY_SAFE", "PUBLISH_LOCK_STRICT", "SECURITY_REDACTION"):
            if flag not in text:
                findings.append(
                    _hint("MEDIUM", "flag_doc_gap", f"{flag} missing from flag governance", "Update SSOT doc"),
                )
    return findings


def check_complexity_budget_hints(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    tools_dir = repo / "tools"
    tool_count = len(list(tools_dir.glob("*.py"))) if tools_dir.is_dir() else 0
    if tool_count > 35:
        findings.append(
            _hint(
                "LOW",
                "tool_proliferation",
                f"{tool_count} tools/*.py files — review complexity budget",
                "Consolidate read-only tools before adding new ones",
            ),
        )
    make_path = repo / "Makefile"
    if make_path.is_file():
        targets = len(re.findall(r"^[a-zA-Z0-9_.-]+:", make_path.read_text(encoding="utf-8"), re.M))
        if targets > 55:
            findings.append(
                _hint(
                    "LOW",
                    "makefile_targets",
                    f"~{targets} Makefile targets — operator surface growing",
                    "Document in complexity_budget.md; avoid duplicate targets",
                ),
            )
    return findings


def check_feature_creep(repo: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    config = repo / "app/config.py"
    if config.is_file():
        text = config.read_text(encoding="utf-8")
        env_bools = len(re.findall(r'_env_bool\("', text))
        if env_bools > 45:
            findings.append(
                _hint(
                    "LOW",
                    "env_surface",
                    f"Large env surface ({env_bools} _env_bool calls) — gate new flags",
                    "Use feature_flag_governance.md + default off",
                ),
            )
    return findings


def check_experimental_scope(repo: Path) -> list[dict[str, str]]:
    """Scan RFC / backlog docs for platform-creep language (exclude anti-creep policy docs)."""
    findings: list[dict[str, str]] = []
    paths: list[Path] = []
    rfc = repo / "docs" / "rfc"
    if rfc.is_dir():
        paths.extend(rfc.rglob("*.md"))
    backlog = repo / "docs" / "POST_V1_TODO_BACKLOG.md"
    if backlog.is_file():
        paths.append(backlog)
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = str(path.relative_to(repo))
        for line in lines:
            lower = line.lower()
            if any(x in lower for x in ("reject", "not a", "non-goal", "unsupported", "out of scope")):
                continue
            for pattern, code in CREEP_PATTERNS:
                if re.search(pattern, line, re.I):
                    findings.append(
                        _hint(
                            "LOW",
                            f"creep_{code}",
                            f"Pattern '{code}' in {rel} — mark experimental or unsupported",
                            "See architectural_preservation.md",
                        ),
                    )
                    break
    return findings[:8]


def check_unsupported_scaling() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for combo, msg in UNSUPPORTED_ENV:
        if all(_env_on(k) == (v == "1") for k, v in combo.items()):
            if combo.get("PUBLISH_LOCK_STRICT") == "0" and _env_on("REDIS_ENABLED"):
                findings.append(
                    _hint("HIGH", "unsupported_scaling", msg, "Enable PUBLISH_LOCK_STRICT or reduce workers"),
                )
    return findings


def run_guardrails(*, repo: Path | None = None) -> dict[str, Any]:
    root = repo or REPO
    findings: list[dict[str, str]] = []
    findings.extend(check_strategy_docs(root))
    findings.extend(check_adr_linkage(root))
    findings.extend(check_governance_consistency(root))
    findings.extend(check_complexity_budget_hints(root))
    findings.extend(check_feature_creep(root))
    findings.extend(check_experimental_scope(root))
    findings.extend(check_unsupported_scaling())

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
        "checks": {
            "strategy_docs": "OK" if not any(f["code"] == "missing_strategy_doc" for f in findings) else "FAIL",
            "adr_linkage": "OK",
            "governance_consistency": "OK",
            "complexity_hints": "OK",
            "feature_creep": "OK",
            "experimental_scope": "OK",
        },
        "note": "Stewardship hints only — not a merge blocker unless --strict",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true", help="Exit 1 on HIGH findings")
    p.add_argument("--fail-on", default="HIGH", choices=["LOW", "MEDIUM", "HIGH"])
    args = p.parse_args()

    report = run_guardrails()
    threshold = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}[args.fail_on]
    worst = 0
    for f in report.get("findings") or []:
        worst = max(worst, {"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(f.get("severity", ""), 0))
    if args.strict and worst >= threshold:
        report["status"] = "FAIL"

    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
