"""Freeze integrity checks (post v3.2 tooling freeze). Read-only."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, FROZEN_SCHEMA_VERSION
from utils.ops_tooling import frozen_utc_now

FREEZE_TAG = "v3.2-operational-tooling-freeze"
INTEGRITY_REPORT_SCHEMA_VERSION = 1

RUNTIME_WATCH_PATHS = (
    "publisher",
    "collector",
    "app/main.py",
    "app/config.py",
    "observability/runtime_contracts.py",
)

FORBIDDEN_REPO_PATHS = (
    "tools/ops_telemetry_server.py",
    "tools/ops_daemon.py",
    "tools/telemetry_ingest.py",
    "docker-compose.ops-telemetry.yml",
    "deploy/ops-dashboard",
)

OPS_TOOLING_GLOBS = (
    "tools/ops_*.py",
    "tools/validate_ops*.py",
    "tools/export_ops*.py",
    "tools/build_ops*.py",
    "tools/generate_ops*.py",
    "tools/check_freeze*.py",
    "tools/build_stewardship*.py",
)

NETWORK_IMPORTS = frozenset({"requests", "httpx", "aiohttp", "urllib.request", "socket"})

RUNTIME_IMPORT_PREFIXES = (
    "publisher.publish_service",
    "publisher.telegram_publisher",
    "collector.service",
    "app.main",
)


def _git_diff_since_freeze(repo_root: Path, paths: tuple[str, ...]) -> tuple[str, list[str]]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", f"{FREEZE_TAG}..HEAD", "--", *paths],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "SKIP", ["git_unavailable"]
    if proc.returncode != 0:
        return "WARN", [f"git_diff_failed:{proc.stderr.strip()[:200]}"]
    files = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return ("FAIL", files) if files else ("OK", [])


def _scan_ops_tooling_imports(repo_root: Path) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for pattern in OPS_TOOLING_GLOBS:
        for path in repo_root.glob(pattern):
            if path.name == "live_telegram_diagnostics.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for mod in NETWORK_IMPORTS:
                if re.search(rf"^\s*(import|from)\s+{re.escape(mod)}\b", text, re.M):
                    issues.append({"path": str(path.relative_to(repo_root)), "issue": f"network_import:{mod}"})
            for prefix in RUNTIME_IMPORT_PREFIXES:
                if re.search(rf"^\s*(import|from)\s+{re.escape(prefix)}", text, re.M):
                    issues.append({"path": str(path.relative_to(repo_root)), "issue": f"runtime_import:{prefix}"})
    return issues


def _contracts_frozen_check() -> tuple[str, list[str]]:
    issues: list[str] = []
    if FROZEN_SCHEMA_VERSION != 1:
        issues.append(f"unexpected_frozen_schema_version:{FROZEN_SCHEMA_VERSION}")
    if len(FROZEN_ARTIFACT_FILENAMES) != 14:
        issues.append(f"artifact_count_not_14:{len(FROZEN_ARTIFACT_FILENAMES)}")
    return ("FAIL", issues) if issues else ("OK", [])


def build_freeze_integrity_report(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[1]
    checks: list[dict[str, Any]] = []

    rt_status, rt_files = _git_diff_since_freeze(root, RUNTIME_WATCH_PATHS)
    checks.append(
        {
            "id": "runtime_paths_since_freeze",
            "status": rt_status,
            "detail": rt_files,
            "freeze_tag": FREEZE_TAG,
        }
    )

    forbidden_hits: list[str] = []
    for rel in FORBIDDEN_REPO_PATHS:
        if (root / rel).exists():
            forbidden_hits.append(rel)
    checks.append(
        {
            "id": "forbidden_paths_absent",
            "status": "FAIL" if forbidden_hits else "OK",
            "detail": forbidden_hits,
        }
    )

    c_status, c_issues = _contracts_frozen_check()
    checks.append({"id": "runtime_contracts_frozen", "status": c_status, "detail": c_issues})

    import_issues = _scan_ops_tooling_imports(root)
    checks.append(
        {
            "id": "tooling_offline_imports",
            "status": "FAIL" if import_issues else "OK",
            "detail": import_issues,
        }
    )

    freeze_doc = root / "docs/releases/v3_2_immutable_baseline.md"
    checks.append(
        {
            "id": "immutable_baseline_doc",
            "status": "OK" if freeze_doc.is_file() else "FAIL",
            "detail": [] if freeze_doc.is_file() else ["missing_doc"],
        }
    )

    fail = sum(1 for c in checks if c["status"] == "FAIL")
    warn = sum(1 for c in checks if c["status"] == "WARN")
    status = "FAIL" if fail else ("WARNING" if warn else "OK")

    return {
        "schema_version": INTEGRITY_REPORT_SCHEMA_VERSION,
        "read_only": True,
        "offline": True,
        "generated_at": frozen_utc_now(),
        "freeze_tag": FREEZE_TAG,
        "status": status,
        "checks": checks,
        "summary": {"fail": fail, "warn": warn, "pass": len(checks) - fail - warn},
    }


def integrity_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Freeze integrity report",
        "",
        f"Generated: {report.get('generated_at')}",
        f"Status: **{report.get('status')}**",
        f"Freeze tag: `{report.get('freeze_tag')}`",
        "",
        "## Checks",
        "",
        "| ID | Status | Detail |",
        "|----|--------|--------|",
    ]
    for c in report.get("checks") or []:
        detail = c.get("detail")
        if isinstance(detail, list):
            d = ", ".join(str(x) for x in detail[:8]) or "—"
        else:
            d = str(detail)
        lines.append(f"| {c.get('id')} | {c.get('status')} | {d} |")
    lines.append("")
    return "\n".join(lines)


def write_json_deterministic(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
